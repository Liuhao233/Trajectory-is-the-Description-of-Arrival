import torch
import torch.nn as nn
import pickle as pkl
import numpy as np
from torch.utils.data.dataset import Dataset
from torch.utils.data.dataloader import DataLoader
import torch.nn.functional as F
HIDDEN_SIZE = 256
from tqdm import tqdm

device = "cuda:0"
class edge_dataset(Dataset):
    def __init__(self, sample, y, vocal_max):
        """

        Args:
            sample: List[path]
            arrival: List[node]
            vocal_max: len of geohash
            K: neg length
        """
        super(edge_dataset, self).__init__()
        self.vocal_max = vocal_max
        self.T = max([len(v) for v in sample])
        self.sample = []
        for sen in tqdm(sample):
            senpad = np.zeros(self.T, np.long)
            senpad[:len(sen)] = np.array(sen) + 1 # shift one position to contain padding 0
            self.sample.append(senpad)
        self.arrival = y
        self.paths = torch.LongTensor(self.sample)  # (N,T)
        self.nodes = torch.FloatTensor(self.arrival).view(-1,2)  # (N,2)

    def __len__(self):
        return len(self.sample)

    def __getitem__(self, idx):
        return self.paths[idx],  self.arrival[idx]
class mlp(nn.Module):
    def __init__(self,vocal_max):
        super(mlp, self).__init__()
        self.embed = nn.Embedding(vocal_max+1,32,padding_idx=0) # padding
        self.conv = nn.Conv1d(32,32,kernel_size=3,padding=1)
        self.fc1 = nn.Linear(32,HIDDEN_SIZE)
        self.fc2 = nn.Linear(HIDDEN_SIZE,2)
        self.dropout = nn.Dropout(0.5)
    def forward(self,x):
        embedding = self.embed(x) # B,T,32
        embedding = embedding.permute(0,2,1) # B,C,T
        l1 = F.relu(self.conv(embedding))
        l1_max = torch.max(l1,dim=-1)[0] # B,32 over-time-maxpooling
        l2 = self.dropout(F.relu(self.fc1(l1_max)))
        return self.fc2(l2)

if __name__ == '__main__':
    model = mlp(56960).to(device)
    optim = torch.optim.Adam(model.parameters(),0.01)
    critic = torch.nn.MSELoss()
    with open("../train_data.pth", 'rb') as f:
        X, y = pkl.load(f)
    size = len(X)
    print("[INFO] load dataset")
    train_dataloader = DataLoader(edge_dataset(X[:round(size*0.95)],y[:round(size*0.95)],56960),200,True,drop_last=True)
    test_data = edge_dataset(X[round(size*0.95):],y[round(size*0.95):],56960)
    test_dataloader = DataLoader(test_data,len(test_data))
    print("[INFO] finish")
    X_test,y_test = None,None
    for x,y in test_dataloader:
        X_test = x.to(device)
        y_test = y.to(device)
    error_best = 100
    for epoch in range(100):
        acc = 0
        n = 0
        tbar = tqdm(train_dataloader)
        model.train()
        for X,y in tbar:
            pred = model(X.to(device))
            loss = critic(pred,y.to(device).float())
            optim.zero_grad()
            loss.backward()
            optim.step()
            tbar.set_postfix({'loss':"%.3f"%loss.cpu().detach().item()})
        model.eval()
        pred = model(X_test).detach()
        err = critic(pred,y_test).cpu().detach().item()
        print(f"epoch {epoch} mse is {err:.3f}")
        if err<error_best:
            error_best = err
            torch.save(model.state_dict(),"model_best.pt")

