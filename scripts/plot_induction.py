import os
import matplotlib.pyplot as plt

nesy_exp_dir = "../exp_induction"
sft_exp_dir = "../exp_induction_sft"
selected_epoch = 10

nesy_observed_samples = []
nesy_seen_induction_accuracy = []
nesy_unseen_induction_accuracy = []

for exp_name in os.listdir(nesy_exp_dir):
    if "vae" in exp_name:
        exp_path = os.path.join(nesy_exp_dir, exp_name)
        observed_sample = int(exp_name.split("induction-")[1])
        find_seen_induction_accuracy = False
        find_unseen_induction_accuracy = False
        if os.path.isdir(exp_path):
            induction_path = os.path.join(exp_path, f"epoch{selected_epoch}", "neural2symbolic.log")
            try:
                with open(induction_path, "r") as f:
                    # 分别找到seen task accuracy和unseen task accuracy
                    lines = f.readlines()
                    for line in lines:
                        if "accuracy on seen task" in line:
                            find_seen_induction_accuracy = True
                            this_seen_induction_accuracy = float(line.split("samples: ")[1].split(" ")[0])
                        elif "accuracy on unseen task" in line:
                            find_unseen_induction_accuracy = True
                            this_unseen_induction_accuracy = float(line.split("samples: ")[1].split(" ")[0])

            except Exception as e:
                print(f"Error reading file {induction_path}: {e}")
                continue
            
            if find_seen_induction_accuracy and find_unseen_induction_accuracy:
                nesy_observed_samples.append(observed_sample)
                nesy_seen_induction_accuracy.append(this_seen_induction_accuracy)
                nesy_unseen_induction_accuracy.append(this_unseen_induction_accuracy)


sft_observed_samples = []
sft_seen_induction_accuracy = []
sft_unseen_induction_accuracy = []

for exp_name in os.listdir(sft_exp_dir):
    if "finetuning" in exp_name:
        exp_path = os.path.join(sft_exp_dir, exp_name)
        observed_sample = int(exp_name.split("finetuning-")[1])
        find_seen_induction_accuracy = False
        find_unseen_induction_accuracy = False
        if os.path.isdir(exp_path):
            induction_path = os.path.join(exp_path, "symbolic_task.log")
            try:
                with open(induction_path, "r") as f:
                    # 分别找到seen task accuracy和unseen task accuracy
                    lines = f.readlines()
                    for line in lines:
                        if "symbolic seen task accuracy" in line:
                            find_seen_induction_accuracy = True
                            this_seen_induction_accuracy = float(line.split("finetuning: ")[1].split(" ")[0])
                        elif "symbolic unseen task accuracy" in line:
                            find_unseen_induction_accuracy = True
                            this_unseen_induction_accuracy = float(line.split("finetuning: ")[1].split(" ")[0])

            except Exception as e:
                print(f"Error reading file {induction_path}: {e}")
                continue
            
            if find_seen_induction_accuracy and find_unseen_induction_accuracy:
                sft_observed_samples.append(observed_sample)
                sft_seen_induction_accuracy.append(this_seen_induction_accuracy)
                sft_unseen_induction_accuracy.append(this_unseen_induction_accuracy)

# 将所有列表按pretrain_ratios升序排序
if len(nesy_observed_samples) > 0:
    nesy_observed_samples, nesy_seen_induction_accuracy, nesy_unseen_induction_accuracy \
    = zip(*sorted(zip(nesy_observed_samples, nesy_seen_induction_accuracy, nesy_unseen_induction_accuracy), key=lambda x: x[0]))
    nesy_induction_accuracy = [0.9 * seen + 0.1 * unseen for seen, unseen in zip(nesy_seen_induction_accuracy, nesy_unseen_induction_accuracy)]
    plt.plot(nesy_observed_samples, nesy_induction_accuracy, label="NesyVaiBot", color='#2ecc71', marker='o')
    # plt.plot(nesy_observed_samples, nesy_seen_induction_accuracy, label="NesyVaiBot-seen", color='#2ecc71', marker='o', linestyle='-')
    # plt.plot(nesy_observed_samples, nesy_unseen_induction_accuracy, label="NesyVaiBot-unseen", color='#2ecc71', marker='o', linestyle='--')

if len(sft_observed_samples) > 0:
    sft_observed_samples, sft_seen_induction_accuracy, sft_unseen_induction_accuracy \
    = zip(*sorted(zip(sft_observed_samples, sft_seen_induction_accuracy, sft_unseen_induction_accuracy), key=lambda x: x[0]))
    sft_induction_accuracy = [0.9 * seen + 0.1 * unseen for seen, unseen in zip(sft_seen_induction_accuracy, sft_unseen_induction_accuracy)]
    plt.plot(sft_observed_samples, sft_induction_accuracy, label="SFT", color='#3498db', marker='o')
    # plt.plot(sft_observed_samples, sft_seen_induction_accuracy, label="SFT-seen", color='#3498db', marker='o', linestyle='-')
    # plt.plot(sft_observed_samples, sft_unseen_induction_accuracy, label="SFT-unseen", color='#3498db', marker='o', linestyle='--')

#横轴标签：pretrain ratio
plt.xlabel("observed samples")
plt.ylabel("accuracy")
plt.grid(True)
plt.legend(loc='lower right')
plt.savefig("induction.pdf", bbox_inches='tight')

