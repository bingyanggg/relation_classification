from __future__ import print_function
import numpy as np
np.random.seed(1337)  # for reproducibility
import gzip


import sys
if (sys.version_info > (3, 0)):
    import pickle as pkl
else: #Python 2.7 imports
    import cPickle as pkl


batch_size = 64
test_batch_size = 2717

nb_filter = 200
nb_epoch = 100

filter_length = 3
embedding_dims = 200
position_dims = 25
hidden_dims = embedding_dims + 2*position_dims
log_interval = 10
learning_rate = 0.001

print("Load dataset")
f = gzip.open('pkl/sem-relations-rnn-med-dim.pkl.gz', 'rb')
data = pkl.load(f)
f.close()

embeddings = data['wordEmbeddings']
yTrain, sentenceTrain, positionTrain1, positionTrain2, positionIndexTrain, sdpWeightTrain = data['train_set']
yTest, sentenceTest, positionTest1, positionTest2, positionIndexTest, sdpWeightTrain  = data['test_set']

max_position = max(np.max(positionTrain1), np.max(positionTrain2), np.max(positionTest1), np.max(positionTest2))+1

n_out = max(yTrain)+1
max_sentence_len = sentenceTrain.shape[1]

print("sentenceTrain: ", sentenceTrain.shape)
print("positionTrain1: ", positionTrain1.shape)
print("positionTrain2: ", positionTrain2.shape)
print("yTrain: ", yTrain.shape)
#print("positionIndexTrain: ", positionIndexTrain.shape)
print("sentenceTest: ", sentenceTest.shape)
print("positionTest1: ", positionTest1.shape)
print("positionTest2: ", positionTest2.shape)
print("yTest: ", yTest.shape)
#print("positionIndexTest: ", positionIndexTest.shape)
print("Embeddings: ",embeddings.shape)

import torch
from torch.autograd import Variable
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.utils.data as D
import random


class CnnOneAttNet(nn.Module):
    def __init__(self):
        super(CnnOneAttNet, self).__init__()
        self.emb1 = nn.Embedding(embeddings.shape[0], embeddings.shape[1])
        self.emb1.weight.data.copy_(torch.from_numpy(embeddings))
        self.emb2 = nn.Embedding(max_position, position_dims)
        #self.emb3 = nn.Embedding(max_position, position_dims)
        #self.conv = nn.Conv1d(embedding_dims+2*position_dims, nb_filter, kernel_size=filter_length, padding=1)
        #self.drop = nn.Dropout(0)
        #self.fc = nn.Linear(nb_filter, n_out)
        #self.softmax = nn.Softmax()
        self.lstm = nn.LSTM(embedding_dims+2*position_dims, hidden_dims, batch_first=True, bidirectional=True)
        #self.h0 = Variable(torch.randn(2, batch_size, hidden_dims))
        #self.c0 = Variable(torch.randn(2, batch_size, hidden_dims))
        self.conv = nn.Conv1d(4*hidden_dims, nb_filter, kernel_size=filter_length, padding=1)
        self.drop = nn.Dropout(0)
        self.fc = nn.Linear(nb_filter, n_out)
     
    def forward(self, words, pos1, pos2):
        embed1 = self.emb1(words)
        embed2 = self.emb2(pos1)
        embed3 = self.emb2(pos2)
        x = torch.cat([embed1, embed2, embed3], 2)
        output, (hn, cn) = self.lstm(x)#, (self.h0, self.c0))
        o1, o2 = output.chunk(2, dim=2)
        o1_1 = o1[:,0:o1.shape[1]-1,:]
        o1_2 = o1[:,1:,:]
        o1 = torch.cat((o1_1, o1_2), 2).permute(0, 2, 1)
        o2_1 = o2[:,0:o2.shape[1]-1,:]
        o2_2 = o2[:,1:,:]
        o2 = torch.cat((o2_1, o2_2), 2).permute(0, 2, 1)
        #x = torch.max(F.relu(self.conv(output.permute(0, 2, 1))), 2)[0]
        x = torch.max(F.relu(self.conv(torch.cat((o1, o2), 1))), 2)[0]
        x = self.fc(self.drop(x))
        #x = self.softmax(x)
        return x

model = CnnOneAttNet()
print(model)
optimizer = optim.Adam(model.parameters(), lr=learning_rate)
#for param in model.parameters():
#    print(type(param.data), param.size())

indexes = range(sentenceTrain.shape[0])
random.shuffle(indexes)
test_indexes = range(sentenceTest.shape[0])
random.shuffle(test_indexes)

def generate(data, batch_size, indexes):    
    data_for_batch = []
    size = data.shape[0]/batch_size
    #if data.shape[0]%batch_size != 0:
    #    size += 1
    #print(batch_size)
    for i in range(size):
        index_for_batch = indexes[batch_size*i:min(data.shape[0], batch_size*(i+1))]
        data_for_batch.append(data[index_for_batch])
    return data_for_batch 

def train(epoch):
    model.train()
    sentence = generate(sentenceTrain, batch_size, indexes)
    position1 = generate(positionTrain1, batch_size, indexes)
    position2 = generate(positionTrain2, batch_size, indexes)
    labels = generate(yTrain, batch_size, indexes)
    for i in range(len(sentence)):
        sentence[i], position1[i], position2[i], labels[i] = Variable(torch.from_numpy(sentence[i])), \
            Variable(torch.from_numpy(position1[i])), Variable(torch.from_numpy(position2[i])), Variable(torch.from_numpy(labels[i]))
        optimizer.zero_grad()
        output = model(sentence[i], position1[i], position2[i])
        loss = F.cross_entropy(output, labels[i])
        loss.backward()
        optimizer.step()
        if i % log_interval == 0:
            #print('Epoch: [{0}]:[{1}/{2}]'.format(epoch,i,loss.data[0]))
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, i * len(sentence[i]), sentenceTrain.shape[0],
                100. * i / (len(sentence)-1), loss.data[0]))

from sklearn.metrics import precision_recall_fscore_support
max_prec, max_rec, max_acc, max_f1 = 0,0,0,0

def test():
    model.eval()
    test_loss = 0
    correct = 0
    sentence = generate(sentenceTest, test_batch_size, test_indexes)
    position1 = generate(positionTest1, test_batch_size, test_indexes)
    position2 = generate(positionTest2, test_batch_size, test_indexes)
    labels = generate(yTest, test_batch_size, test_indexes)
    prediction = np.zeros_like(yTest)
    #print(prediction.shape)
    for i in range(len(sentence)):
        sentence[i], position1[i], position2[i], labels[i] = Variable(torch.from_numpy(sentence[i])), \
            Variable(torch.from_numpy(position1[i])), Variable(torch.from_numpy(position2[i])), Variable(torch.from_numpy(labels[i]))
        output = model(sentence[i], position1[i], position2[i])
        test_loss += F.cross_entropy(output, labels[i]).data[0]
        pred = output.data.max(1, keepdim=True)[1]
        correct += pred.eq(labels[i].data.view_as(pred)).long().cpu().sum()
        prediction[i*test_batch_size:(i+1)*test_batch_size] = pred.squeeze(1)

    test_loss /= sentenceTest.shape[0]
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, sentenceTest.shape[0],
        100. * correct / sentenceTest.shape[0]))
    global max_acc, max_rec, max_prec, max_f1
    #max_acc = max(max_acc, 100. * correct / sentenceTest.shape[0])
    prec, rec, f1, acc = precision_recall_fscore_support(yTest[test_indexes], prediction, average='weighted')
    max_acc = max(max_acc, acc)
    max_prec = max(max_prec, prec)
    max_rec = max(max_rec, rec)
    max_f1 = max(max_f1, f1)

print("Start training")
for epoch in range(nb_epoch):       
    train(epoch)
    test()
    print("Max precision: %.4f" % max_prec)
    print("Max recall: %.4f" % max_rec)
    print("Max f1: %.4f\n" % max_f1)
    #print("Max accuracy: %.4f\n" % max_acc)
