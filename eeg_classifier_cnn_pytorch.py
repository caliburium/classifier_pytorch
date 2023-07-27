import os
import math
import mat73
import numpy as np

import scipy
from scipy import signal
import scipy.io as sio

import torch
from torch import nn

from sklearn.model_selection import KFold
from tqdm import tqdm
from datetime import datetime

device = 'cuda' if torch.cuda.is_available() else 'cpu'


def ext_spectrogram(epoch, fs=1000, window='hamming', nperseg=2000, noverlap=1975, nfft=3000):
    dat = []
    for i in range(epoch.shape[2]):
        tfreq = []
        for j in range(epoch.shape[0]):
            f, t, Sxx = signal.stft(epoch[j, :, i], fs=fs, window=window, nperseg=nperseg, noverlap=noverlap, nfft=nfft)
            # interval = f[-1] / (len(f) - 1)
            # req_len = int(40 / interval)
            tfreq.append(np.abs(Sxx[:121, -41:]).transpose())  # use frequency(~121th) and tiem(-41th~0)
        dat.append(np.asarray(tfreq))
    return np.array(dat)  # shape : (trials, channel number, time, freq), time and freq should be : 41, 121


def get_batch_num(data, batch_size):
    total_len = data.shape[0]
    return math.ceil(total_len / batch_size)


def get_batch(data, batch_size, idx):
    batch_num = get_batch_num(data, batch_size)
    if idx == batch_num - 1:  # last batch
        return data[batch_size * idx:]
    else:
        return data[batch_size * idx:batch_size * (idx + 1)]


def load_data_labels(location='dataset_original2.mat'):  # input: location
    try:
        data = sio.loadmat(location)  # load eeg data
    except:
        data = mat73.loadmat(location)

    ep = ext_spectrogram(data['ep']).reshape(data['ep'].shape[2], -1)
    lb_maxrel = data['lb_maxrel'].T
    lb_pmb28 = data['lb_pmb28'].T
    lb_pmb37 = data['lb_pmb37'].T
    lb_act = data['lb_act'].T
    np.random.seed(2121)
    shuffle_idx = np.random.permutation(lb_maxrel.shape[0])
    # output: train_x, train_y, test_x, test_y
    return ep[shuffle_idx], lb_maxrel[shuffle_idx], lb_pmb28[shuffle_idx], lb_pmb37[shuffle_idx], lb_act[shuffle_idx]


def load_data(location='dataset_original2.mat', is_total=False):
    data = sio.loadmat(location)
    ep = ext_spectrogram(data['ep']).reshape(data['ep'].shape[2], -1)
    lb = data['lb'].T
    if is_total:
        np.random.seed(2121)
        shuffle_idx = np.random.permutation(lb.shape[0])
        return ep[shuffle_idx], lb[shuffle_idx]
    else:
        shuffle_idx = np.random.permutation(lb.shape[0])
        ep = ep[shuffle_idx]
        lb = lb[shuffle_idx]
        num_train = int(ep.shape[0] * 9 / 10)
        return ep[:num_train], lb[:num_train], ep[num_train:], lb[num_train:]


class torch_net(nn.Module):  # CNN (batch_size, num_channels, height, width)
    def __init__(self, num_input):
        super(torch_net, self).__init__()
        self.num_input = num_input
        self.keep_prob = 0.5
        # image size = [22, 19844]
        self.layer1 = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=7, stride=1, padding=3),  # padding https://ardino.tistory.com/40
            nn.Tanh(),
            nn.MaxPool2d(kernel_size=2, stride=2))
        self.layer2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=5, stride=1, padding=2),
            nn.Tanh(),
            nn.MaxPool2d(kernel_size=2, stride=2))
        self.layer3 = nn.Sequential(
            nn.Conv2d(64, 256, kernel_size=5, stride=1, padding=2),
            nn.Tanh(),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=1))

        # pytorch (batch_size, num_channels, height, width)
        # torch.Size([22, 256, 31, 11])
        self.fc1 = torch.nn.Linear(31 * 11 * 256, 512, bias=True)
        torch.nn.init.xavier_uniform_(self.fc1.weight)
        self.layer4 = torch.nn.Sequential(
            self.fc1,
            torch.nn.ReLU(),
            torch.nn.Dropout(p=1 - self.keep_prob))

        self.fc2 = torch.nn.Linear(512, 2, bias=True)
        torch.nn.init.xavier_uniform_(self.fc2.weight)

    def forward(self, x):
        out = self.layer1(x)
        out = self.layer2(out)
        out = self.layer3(out)
        # print(out.shape, "conv")
        out = torch.flatten(out, start_dim=1)
        # print(out.shape, "flattened")
        out = self.layer4(out)
        out = self.fc2(out)
        return out


print("main")
save_all = False

if save_all:
    eps = []
    lbs = []
    for dataset in [0, 1, 5]:  # for dataset in [0]:
        if not os.path.exists(f'./dataset{dataset}'):
            os.mkdir(f'./dataset{dataset}')
        print(f'dataset{dataset}')
        ep_tot, lb_tot = load_data(f'dataset{dataset}_parsed.mat', is_total=True)
        eps.append(ep_tot)
        lbs.append(lb_tot)

print("loading...subi")
ep_tots = []
lb_tots = []
strings_ = "./logs4_" + datetime.today().strftime('%Y%m%d-%H%M') + "/"

for subi in [0]:  # in range(33):
    ep_tots_, lb_maxrel_tot, lb_pmb28_tot, lb_pmb37_tot, lb_act_tot \
        = load_data_labels('./dat_sub/sub{0}.mat'.format(subi + 1))
    ep_tots_ = (ep_tots_.reshape(ep_tots_.shape[0], 16, -1))[:, :4, :]
    ep_tots_ = torch.tensor(ep_tots_, dtype=torch.float)  # Convert to PyTorch tensor and specify data type
    ep_tots_ = torch.transpose(ep_tots_, 1, 2)  # Swap axes using torch.transpose
    print(ep_tots_.shape)
    ep_tots_ = ep_tots_.reshape(ep_tots_.shape[0], -1)
    if len(ep_tots) == 0:
        ep_tots = ep_tots_
    else:
        ep_tots = torch.cat((ep_tots, ep_tots_), dim=0)  # Use torch.cat for concatenating tensors
    if len(lb_tots) == 0:
        lb_tots.append(lb_maxrel_tot)
        lb_tots.append(lb_pmb28_tot)
        lb_tots.append(lb_pmb37_tot)
        lb_tots.append(lb_act_tot)
    else:
        lb_tots[0] = np.concatenate((lb_tots[0], lb_maxrel_tot), axis=0)
        lb_tots[1] = np.concatenate((lb_tots[1], lb_pmb28_tot), axis=0)
        lb_tots[2] = np.concatenate((lb_tots[2], lb_pmb37_tot), axis=0)
        lb_tots[3] = np.concatenate((lb_tots[3], lb_act_tot), axis=0)

print("loading...lbi")
strings_ = "./logs" + datetime.today().strftime('%Y%m%d-%H%M') + "_subgroup_4ch/"
kf = KFold(n_splits=10, shuffle=False)
for lbi in [0]:
    lb_tot = lb_tots[lbi]
    lb1idx = np.where(lb_tot == 0)[0]
    lb2idx = np.where(lb_tot == 1)[0]
    minidx = min(lb1idx.shape[0], lb2idx.shape[0])
    lb1idx = lb1idx[:minidx]
    lb2idx = lb2idx[:minidx]
    lb_tot = np.concatenate((lb_tot[lb1idx], lb_tot[lb2idx]))
    ep_tot = np.concatenate((ep_tots[lb1idx, :], ep_tots[lb2idx, :]), axis=0)

    c = -1 / (np.sqrt(2) * scipy.special.erfcinv(3 / 2))
    mad_ = c * np.median(np.abs(ep_tot - np.median(ep_tot, axis=1).reshape(-1, 1)), axis=1)
    ep_tot = ep_tot[np.where(mad_ < 3)[0], :]
    lb_tot = lb_tot[np.where(mad_ < 3)[0]]

    np.random.seed(2020)
    index = np.random.permutation(ep_tot.shape[0])
    ep_tot = ep_tot[index, :]
    lb_tot = lb_tot[index]

    kf.get_n_splits(lb_tot)
    cv = 0
    batch_size = 22

    print("start training")
    for train_ind, test_ind in kf.split(lb_tot):
        ep, lb = ep_tot[train_ind], lb_tot[train_ind]
        test_x, test_y = ep_tot[test_ind], lb_tot[test_ind]
        ep = ep.reshape(ep.shape[0], 4, 121, 41)
        test_x = test_x.reshape(test_x.shape[0], 4, 121, 41)
        temp1 = np.concatenate((ep[:, 0, :, :], ep[:, 1, :, :]), axis=1)
        temp2 = np.concatenate((ep[:, 2, :, :], ep[:, 3, :, :]), axis=1)
        ep = np.concatenate((temp1, temp2), axis=2).reshape((ep.shape[0], 121 * 2, 41 * 2, 1))

        temp1 = np.concatenate((test_x[:, 0, :, :], test_x[:, 1, :, :]), axis=1)
        temp2 = np.concatenate((test_x[:, 2, :, :], test_x[:, 3, :, :]), axis=1)
        test_x = np.concatenate((temp1, temp2), axis=2).reshape((test_x.shape[0], 121 * 2, 41 * 2, 1))

        # print(ep.shape)  # tensorflow (batch_size, height, width, num_channels)
        ep = torch.transpose(torch.Tensor(ep), 1, 3)
        ep = torch.transpose(torch.Tensor(ep), 2, 3)
        # print(ep.shape, " ~ transposed")  # pytorch (batch_size, num_channels, height, width)

        # ep, lb = ep_tot[train_ind], lb_tot[train_ind]
        # test_x, test_y = ep_tot[test_ind], lb_tot[test_ind]
        cv += 1
        print("Using PyTorch version: ", torch.__version__, 'Device: ', device)
        network = torch_net(num_input=ep.shape[1])

        infoxinfo = []
        epoch = []
        summary = {}
        if not os.path.exists('./cv{0}'.format(cv)):
            os.mkdir('./cv{0}'.format(cv))

        criterion = torch.nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(network.parameters(), lr=0.001)
        batch_size = 22
        batch_num = get_batch_num(ep, batch_size)

        epochs = []
        costs = []

        print('Training starts for CV {0}'.format(cv))
        for epoch in tqdm(range(50)):

            total_cost = 0
            for i in range(batch_num):
                network.zero_grad()
                batch_ep = get_batch(ep, batch_size, i)
                batch_lb = get_batch(lb, batch_size, i)
                batch_ep = torch.Tensor(batch_ep)
                batch_lb = torch.Tensor(batch_lb).long()
                output = network(batch_ep)

                batch_lb = torch.zeros(batch_lb.size(0), 2).scatter_(1, batch_lb.view(-1, 1), 1)

                loss = criterion(output, batch_lb)

                loss.backward()
                optimizer.step()
                total_cost += loss.item()

            costs.append(total_cost)
            epochs.append(epoch)
            print('Epoch [%d/%d], Loss: %.4f' % (epoch + 1, 50, total_cost))

        try:
            del ep, test_x, lb, test_y
        except:
            ''
