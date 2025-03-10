import os
import matplotlib.pyplot as plt

# 设置全局字体为Times New Roman
plt.rcParams['font.family'] = 'serif'

# plt.rcParams['axes.facecolor'] = '#2c3e50'
# plt.rcParams['figure.facecolor'] = '#34495e'

plt.rcParams['grid.color'] = '#7f8c8d'
plt.rcParams['grid.alpha'] = 0.3

def load_data(exp_dir, selected_epoch):

    pretrain_ratios = []
    seen_induction_accuracy = []
    seen_deduction_accuracy = []
    unseen_induction_accuracy = []
    unseen_deduction_accuracy = []

    for exp_name in os.listdir(exp_dir):
        exp_path = os.path.join(exp_dir, exp_name)
        train_ratio = exp_name.split("pretrain-")[1]
        find_seen_induction_accuracy = False
        find_unseen_induction_accuracy = False
        find_seen_deduction_accuracy = False
        find_unseen_deduction_accuracy = False
        if os.path.isdir(exp_path):
            induction_path = os.path.join(exp_path, f"epoch{selected_epoch}", "neural2symbolic.log")
            deduction_path = os.path.join(exp_path, f"epoch{selected_epoch}", "symbolic2neural.log")
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
                with open(deduction_path, "r") as f:
                    lines = f.readlines()
                    for line in lines:
                        if "accuracy on seen task" in line:
                            find_seen_deduction_accuracy = True
                            this_seen_deduction_accuracy = float(line.split("samples: ")[1].split(" ")[0])
                        elif "accuracy on unseen task" in line:
                            find_unseen_deduction_accuracy = True
                            this_unseen_deduction_accuracy = float(line.split("samples: ")[1].split(" ")[0])
            except Exception as e:
                print(f"Error reading file {induction_path} or {deduction_path}: {e}")
                continue
            
            if find_seen_induction_accuracy and find_unseen_induction_accuracy and find_seen_deduction_accuracy and find_unseen_deduction_accuracy:
                pretrain_ratios.append(float(train_ratio))
                seen_induction_accuracy.append(this_seen_induction_accuracy)
                unseen_induction_accuracy.append(this_unseen_induction_accuracy)
                seen_deduction_accuracy.append(this_seen_deduction_accuracy)
                unseen_deduction_accuracy.append(this_unseen_deduction_accuracy)

    # 将所有列表按pretrain_ratios升序排序
    pretrain_ratios, seen_induction_accuracy, unseen_induction_accuracy, seen_deduction_accuracy, unseen_deduction_accuracy \
    = zip(*sorted(zip(pretrain_ratios, seen_induction_accuracy, unseen_induction_accuracy, seen_deduction_accuracy, unseen_deduction_accuracy), key=lambda x: x[0]))

    # 将seen和unseen的accuracy按0.9和0.1的比例混合，得到induction的accuracy
    induction_accuracy = [0.9 * seen + 0.1 * unseen for seen, unseen in zip(seen_induction_accuracy, unseen_induction_accuracy)]

    # 将seen和unseen的accuracy按0.9和0.1的比例混合，得到deduction的accuracy
    deduction_accuracy = [0.9 * seen + 0.1 * unseen for seen, unseen in zip(seen_deduction_accuracy, unseen_deduction_accuracy)]

    # plt.plot(pretrain_ratios, seen_induction_accuracy, label="seen induction", color='#2ecc71')
    # plt.plot(pretrain_ratios, unseen_induction_accuracy, label="unseen induction", color='#3498db')
    # plt.plot(pretrain_ratios, seen_deduction_accuracy, label="seen deduction", color='#e74c3c')
    # plt.plot(pretrain_ratios, unseen_deduction_accuracy, label="unseen deduction", color='#f39c12')

    # 筛选所有pretrain_ratios小于0.005的样本点
    idx = [i for i, pretrain_ratio in enumerate(pretrain_ratios) if pretrain_ratio > 0.01][0]
    pretrain_ratios = pretrain_ratios[:idx]
    induction_accuracy = induction_accuracy[:idx]
    deduction_accuracy = deduction_accuracy[:idx]

    return pretrain_ratios, induction_accuracy, deduction_accuracy


selected_epoch = 1

exp_dir = "../exp_generalize"
pretrain_ratios_sni, induction_accuracy_sni, deduction_accuracy_sni = load_data(exp_dir, selected_epoch)

exp_dir = "../exp_p3_final_generalize"
pretrain_ratios_p3, induction_accuracy_p3, deduction_accuracy_p3 = load_data(exp_dir, selected_epoch)

plt.plot(pretrain_ratios_sni, induction_accuracy_sni, label="induction (SNI)", color='#1abc9c', marker='o', linestyle='-')
plt.plot(pretrain_ratios_sni, deduction_accuracy_sni, label="deduction (SNI)", color='#3498db', marker='o', linestyle='-')

plt.plot(pretrain_ratios_p3, induction_accuracy_p3, label="induction (P3)", color='#1abc9c', marker='o', linestyle='--')
plt.plot(pretrain_ratios_p3, deduction_accuracy_p3, label="deduction (P3)", color='#3498db', marker='o', linestyle='--')

#横轴标签：pretrain ratio
plt.xlabel("pretrain ratio")
plt.ylabel("accuracy")
plt.grid(True)

plt.legend(loc='lower right')
plt.savefig(f"generalization.pdf", bbox_inches='tight')