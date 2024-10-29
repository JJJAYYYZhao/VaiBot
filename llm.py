from multiprocessing import reduction
import os
import re
import random
import torch
import copy
import json
import torch.nn as nn
from peft import (  # noqa: E402
    LoraConfig,
    PeftModel,
    prepare_model_for_kbit_training,
    get_peft_model,
)
from peft import AutoPeftModelForCausalLM
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM, LlamaTokenizer
from utils import mkdir

class WrappedLLM(nn.Module):
    
    def __init__(self, args):
        super(WrappedLLM, self).__init__()
        self.args = args
        self.config = AutoConfig.from_pretrained(args.model_name_or_path)
        self.dtype = torch.bfloat16

        self.task_model = AutoModelForCausalLM.from_pretrained(args.model_name_or_path,
                                                        device_map=self.args.task_device,#"auto",
                                                        torch_dtype=self.dtype, 
                                                        trust_remote_code=True,
                                                        #torch_dtype=torch.float16, 
                                                        #load_in_8bit=True
                                                        )
        
        # self.ori_state_dict = self.task_model.state_dict()
        for params in self.task_model.parameters():
            params.requires_grad = False

        if "llama" in args.model_name_or_path.lower():
            self.tokenizer = LlamaTokenizer.from_pretrained(args.model_name_or_path, use_fast=False, padding_side='right', add_bos_token=False, add_eos_token=True)
        else:
            self.tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, use_fast=False, padding_side='right', add_bos_token=False, add_eos_token=True)
        
        self.tokenizer.padding_side = "left"
        self.tokenizer.pad_token_id = 0

        if args.method == "nesy":
            self.encoder_model = AutoModelForCausalLM.from_pretrained(args.model_name_or_path,
                                                            device_map=self.args.encoder_device,#"auto",
                                                            torch_dtype=self.dtype, 
                                                            trust_remote_code=True,
                                                            #torch_dtype=torch.float16, 
                                                            #load_in_4bit=True
                                                            )
            self.encoder_config = LoraConfig(
                r=args.lora_r,
                lora_alpha=args.lora_alpha,
                target_modules=args.target_modules.split(","),
                fan_in_fan_out=False,
                lora_dropout=0.05,
                inference_mode=False,
                bias="none",
                task_type="FEATURE_EXTRACTION",
            )
            
            self.decoder_model = AutoModelForCausalLM.from_pretrained(args.model_name_or_path,
                                                            device_map=self.args.decoder_device,#"auto",
                                                            torch_dtype=self.dtype,
                                                            trust_remote_code=True,
                                                            #torch_dtype=torch.float16, 
                                                            #load_in_4bit=True
                                                            )
            self.decoder_config = LoraConfig(
                r=args.lora_r,
                lora_alpha=args.lora_alpha,
                target_modules=args.target_modules.split(","),
                fan_in_fan_out=False,
                lora_dropout=0.05,
                inference_mode=False,
                bias="none",
                task_type="CAUSAL_LM",
            )

            if args.load_nesy_ckpt:
                self.load(args.load_nesy_ckpt)
                
            else:
                self.encoder = get_peft_model(self.encoder_model.model, self.encoder_config).to(self.args.encoder_device)
                self.encoder.print_trainable_parameters()
                self.decoder = get_peft_model(self.decoder_model, self.decoder_config).to(self.args.decoder_device)
                self.decoder.print_trainable_parameters()
                self.param_info = self.specify_parameter(n=args.latent_size)
        
        elif args.method == "nesy-pretrain":
            
            self.param_info = self.specify_parameter(n=args.latent_size)


    def save(self, dir):
        self.encoder.save_pretrained(os.path.join(dir, "encoder_lora"))
        self.decoder.save_pretrained(os.path.join(dir, "decoder_lora"))
        json.dump(self.param_info, open(os.path.join(dir, "params_info.json"), "w"))
        
    def load(self, dir):
        self.encoder = PeftModel.from_pretrained(self.encoder_model.model, os.path.join(dir, "encoder_lora")).to(self.args.encoder_device)
        self.decoder = PeftModel.from_pretrained(self.decoder_model, os.path.join(dir, "decoder_lora")).to(self.args.decoder_device)
        self.param_info = json.load(open(os.path.join(dir, "params_info.json"), "r"))

    def specify_parameter(self, n):
        
        if self.args.fuse_method == "delta":
            
            param_counts = {}
        
            selected_layer_id = [f".{31-i}." for i in range(self.args.selected_layers)]
            for name, params in dict(self.task_model.named_parameters()).items():
                if params.dtype == self.dtype and "layers" in name and "_proj" in name:
                    if any([id_ in name for id_ in selected_layer_id]):
                        param_counts[name] = params.view(-1).shape[0]

            param_count_sum = sum(param_counts.values())
            param_allocation = {}
            for name, count in param_counts.items():
                param_allocation[name] = int(n * count / param_count_sum)

            param_info = []
            for name, specified_param_num in param_counts.items():
                params = dict(self.task_model.named_parameters())[name]
                sampled_param_num = param_allocation[name]
                weights = params.view(-1)
                indices = random.sample(range(weights.size(0)), sampled_param_num)
                #selected_weights = weights[indices].detach()
                indices = [[indice % params.shape[0] for indice in indices], [indice // params.shape[0] for indice in indices]]

                param_info.append((name, indices, sampled_param_num))#weights.shape, selected_weights))
        
        else:

            param_info = {}
        
        return param_info
    
    def allocate(self, delta_params):
        
        used_idx = 0
        new_task_parameters = {}
        
        for i in range(len(self.param_info)):

            name, indices, sampled_param_num = self.param_info[i]
            new_weight = delta_params[used_idx:used_idx+sampled_param_num] #+weights
            
            used_idx += sampled_param_num
            new_task_parameters[name] = (indices, new_weight) #new_parameters

        return new_task_parameters
        
    def reset(self):
        
        for i in range(len(self.param_info)):

            name, idx, weight = self.param_info[i]
            dict(self.task_model.named_parameters())[name].view(-1)[idx].copy_(weight)


    def encode(self, inputs):
        
        attention_mask = inputs != self.tokenizer.pad_token_id
        
        outputs = self.encoder(inputs, attention_mask=attention_mask)

        return outputs[0]#.float()
    
    def decode(self, embedding, labels):
        attention_mask = labels != self.tokenizer.pad_token_id
        inputs_embeds = self.decoder_model.model.embed_tokens(labels)#.repeat(embedding.shape[0], 1, 1)
        #labels = labels.repeat(embedding.shape[0], 1)
        # if embedding.dim() == 2:
        #     embedding = embedding.unsqueeze(1)
        soft_token_embedding = embedding.view(embedding.shape[0], self.args.num_soft_token, self.config.hidden_size)
        total_embeds = torch.cat((soft_token_embedding, inputs_embeds), dim=1)
        pad_tokens = torch.full_like(soft_token_embedding[:, :, 0], self.tokenizer.pad_token_id, dtype=torch.int)
        total_labels = torch.cat((pad_tokens, labels), dim=1)
        total_labels[total_labels==self.tokenizer.pad_token_id] = -100
        pad_attention = torch.full_like(soft_token_embedding[:, :, 0], 1, dtype=torch.int)
        total_attention = torch.cat((pad_attention, attention_mask), dim=1)
        outputs = self.decoder(inputs_embeds=total_embeds, attention_mask=total_attention, labels=total_labels)

        return outputs[0]#.float()

    def solve_task(self, x_id, y_id, new_task_parameters, reduce=True):
        
        batch_size = new_task_parameters.shape[0]
        
        if self.args.fuse_method == "delta":
        
            input_ids = torch.cat((x_id, y_id), dim=1)
            pad_tokens = torch.full_like(x_id, self.tokenizer.pad_token_id, dtype=torch.int)
            labels = torch.cat((pad_tokens, y_id), dim=1)
            labels[labels==self.tokenizer.pad_token_id] = -100

            outputs = self.task_model(input_ids=[input_ids, new_task_parameters], labels=labels)

        elif self.args.fuse_method == "p-tuning":
            
            input_ids = torch.cat((x_id, y_id), dim=1)
            inputs_embeds = self.task_model.model.embed_tokens(input_ids)
            
            if self.args.ebm_optim_method == "mc":
                soft_token_embedding = new_task_parameters.view(batch_size*self.args.num_latent_samples, self.args.num_soft_token, self.config.hidden_size)
            else:
                soft_token_embedding = new_task_parameters.view(batch_size, self.args.num_soft_token, self.config.hidden_size)

            attention_mask = input_ids != self.tokenizer.pad_token_id
            pad_attention = torch.full_like(soft_token_embedding[:, :, 0], 1, dtype=torch.int)
            total_attention = torch.cat((pad_attention, attention_mask), dim=1)
            
            total_embeds = torch.cat((soft_token_embedding, inputs_embeds), dim=1)
            pad_tokens_soft = torch.full_like(soft_token_embedding[:, :, 0], self.tokenizer.pad_token_id, dtype=torch.int)
            pad_tokens_x = torch.full_like(x_id, self.tokenizer.pad_token_id, dtype=torch.int)
            total_labels = torch.cat((pad_tokens_soft, pad_tokens_x, y_id), dim=1)
            total_labels[total_labels==self.tokenizer.pad_token_id] = -100

            outputs = self.task_model(inputs_embeds=total_embeds, attention_mask=[total_attention, reduce], labels=total_labels)

        return outputs[0]#.float()

    def predict_task(self, x_id, new_task_parameters=None):
        
        if self.args.fuse_method == "delta":
            
            if new_task_parameters:
                inputs = [x_id, new_task_parameters]
            else:
                inputs = x_id
                
            response = self.task_model.generate(inputs=inputs, 
                                    max_length=x_id.shape[1]+self.args.max_token, 
                                    early_stopping=True,
                                    eos_token_id=self.tokenizer.eos_token_id,
                                    pad_token_id=self.tokenizer.pad_token_id,
                                    # do_sample=do_sample,
                                    # stopping_criteria=stopping_criteria
                                    )

            decoded_tokens = response[0][x_id.shape[1]:]
            
            text = self.tokenizer.decode(decoded_tokens, skip_special_tokens=True)

        elif self.args.fuse_method == "p-tuning":
            
            batch_size = x_id.size(0)
            soft_token_embedding = new_task_parameters.view(batch_size, self.args.num_soft_token, self.config.hidden_size)
            inputs_embeds = self.task_model.model.embed_tokens(x_id)
            total_embeds = torch.cat((soft_token_embedding, inputs_embeds), dim=1)

            attention_mask = x_id != self.tokenizer.pad_token_id
            pad_attention = torch.full_like(soft_token_embedding[:, :, 0], 1, dtype=torch.int)
            total_attention = torch.cat((pad_attention, attention_mask), dim=1)

            response = self.task_model.generate(inputs_embeds=total_embeds,
                                    attention_mask=total_attention,
                                    max_length=x_id.shape[1]+self.args.max_token, 
                                    early_stopping=True,
                                    eos_token_id=self.tokenizer.eos_token_id,
                                    pad_token_id=self.tokenizer.pad_token_id,
                                    # do_sample=do_sample,
                                    # stopping_criteria=stopping_criteria
                                    )
        
            text = [self.tokenizer.decode(response[i], skip_special_tokens=True) for i in range(batch_size)]
        
        return text

    def sample(self, embedding):
        
        # if embedding.dim() == 2:
        #     embedding = embedding.unsqueeze(1)
        embedding = embedding.view(embedding.shape[0], self.args.num_soft_token, self.config.hidden_size)
        
        embedding = embedding.bfloat16()
        
        response = self.decoder_model.generate(inputs_embeds=embedding, 
                                max_length=self.args.max_token, 
                                early_stopping=True,
                                eos_token_id=self.tokenizer.eos_token_id,
                                pad_token_id=self.tokenizer.pad_token_id,
                                # do_sample=do_sample,
                                # stopping_criteria=stopping_criteria
                                )

        return response