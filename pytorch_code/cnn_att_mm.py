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

nb_filter = 100
nb_epoch = 100

filter_length = 3
embedding_dims = 300
position_dims = 30
log_interval = 10
learning_rate = 0.0001

print("Load dataset")
f = gzip.open('pkl/sem-relations.pkl.gz', 'rb')
data = pkl.load(f)
f.close()

embeddings = data['wordEmbeddings']
yTrain, sentenceTrain, positionTrain1, positionTrain2, positionIndexTrain = data['train_set']
yTest, sentenceTest, positionTest1, positionTest2, positionIndexTest  = data['test_set']

max_position = max(np.max(positionTrain1), np.max(positionTrain2))+1

n_out = max(yTrain)+1
max_sentence_len = sentenceTrain.shape[1]
max_prec, max_rec, max_acc, max_f1 = 0,0,0,0

print("sentenceTrain: ", sentenceTrain.shape)
print("positionTrain1: ", positionTrain1.shape)
print("positionTrain2: ", positionTrain2.shape)
print("yTrain: ", yTrain.shape)
print("positionIndexTrain: ", positionIndexTrain.shape)
print("sentenceTest: ", sentenceTest.shape)
print("positionTest1: ", positionTest1.shape)
print("positionTest2: ", positionTest2.shape)
print("yTest: ", yTest.shape)
print("positionIndexTest: ", positionIndexTest.shape)
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
        self.conv = nn.Conv1d(embedding_dims+2*position_dims, nb_filter, kernel_size=filter_length, padding=1)
        self.drop = nn.Dropout(0.25)
        self.fc = nn.Linear(nb_filter, n_out)
        self.softmax = nn.Softmax()
        
    def forward(self, words, pos1, pos2, posIndex):
        emb1 = self.emb1(words)
        emb2 = self.emb2(pos1)
        emb3 = self.emb2(pos2)
        rela = add_att(emb1, posIndex)
        x = torch.cat([emb1, emb2, emb3], 2).permute(0, 2, 1)
        x = torch.max(F.tanh(self.conv(x)*rela), 2)[0]
        x = self.fc(self.drop(x))
        #x = self.softmax(x)
        return x


def add_att(inputs, posIndex):
    words = inputs.permute(0, 2, 1)
    index_vec1 = posIndex[:,0:max_sentence_len].contiguous().view(words.shape[0], 1, -1)
    index_vec2 = posIndex[:,max_sentence_len:2*max_sentence_len].contiguous().view(words.shape[0], 1, -1)
    #print(words.shape, index_vec1.shape)
    rela1 = torch.bmm(index_vec1, torch.bmm(inputs, words))
    rela2 = torch.bmm(index_vec2, torch.bmm(inputs, words))
    rela = torch.cat((rela1, rela2), 1)
    #print(rela1.shape, rela.shape)
    rela = torch.exp(rela)/torch.sum(torch.exp(rela), 2).view(words.shape[0], -1, 1)
    rela = torch.mean(rela, 1).view(words.shape[0], 1, -1)
    #print(rela.shape)
    return rela


model = CnnOneAttNet()
optimizer = optim.Adam(model.parameters(), lr=learning_rate)
#for param in model.parameters():
#    print(type(param.data), param.size())


indexes = range(sentenceTrain.shape[0])
random.shuffle(indexes)
test_indexes = range(sentenceTest.shape[0])
random.shuffle(test_indexes)
def generate(data, batch_size, indexes):    
    data_for_batch = []
    for i in range(data.shape[0]/batch_size):
        index_for_batch = indexes[batch_size*i:min(data.shape[0], batch_size*(i+1))]
        data_for_batch.append(data[index_for_batch])
    return data_for_batch 


def train(epoch):
    model.train()
    sentence = generate(sentenceTrain, batch_size, indexes)
    position1 = generate(positionTrain1, batch_size, indexes)
    position2 = generate(positionTrain2, batch_size, indexes)
    labels = generate(yTrain, batch_size, indexes)
    positionIndex = generate(positionIndexTrain, batch_size, indexes)
    for i in range(len(sentence)):
        sentence[i], position1[i], position2[i], labels[i], positionIndex[i] = Variable(torch.from_numpy(sentence[i])), \
            Variable(torch.from_numpy(position1[i])), Variable(torch.from_numpy(position2[i])), \
            Variable(torch.from_numpy(labels[i])), Variable(torch.from_numpy(positionIndex[i]))
        optimizer.zero_grad()
        output = model(sentence[i], position1[i], position2[i], positionIndex[i])
        loss = F.cross_entropy(output, labels[i])
        loss.backward()
        optimizer.step()
        if i % log_interval == 0:
            #print('Epoch: [{0}]:[{1}/{2}]'.format(epoch,i,loss.data[0]))
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, i * len(sentence[i]), sentenceTrain.shape[0],
                100. * i / (len(sentence)-1), loss.data[0]))


def test():
    model.eval()
    test_loss = 0
    correct = 0
    sentence = generate(sentenceTest, test_batch_size, test_indexes)
    position1 = generate(positionTest1, test_batch_size, test_indexes)
    position2 = generate(positionTest2, test_batch_size, test_indexes)
    labels = generate(yTest, test_batch_size, test_indexes)
    positionIndex = generate(positionIndexTest, test_batch_size, test_indexes)
    for i in range(len(sentence)):
        sentence[i], position1[i], position2[i], labels[i], positionIndex[i] = Variable(torch.from_numpy(sentence[i])), \
            Variable(torch.from_numpy(position1[i])), Variable(torch.from_numpy(position2[i])), \
            Variable(torch.from_numpy(labels[i])), Variable(torch.from_numpy(positionIndex[i]))
        output = model(sentence[i], position1[i], position2[i], positionIndex[i])
        test_loss += F.cross_entropy(output, labels[i]).data[0]
        pred = output.data.max(1, keepdim=True)[1]
        correct += pred.eq(labels[i].data.view_as(pred)).long().cpu().sum()

    test_loss /= sentenceTest.shape[0]
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, sentenceTest.shape[0],
        100. * correct / sentenceTest.shape[0]))
    global max_acc
    max_acc = max(max_acc, 100. * correct / sentenceTest.shape[0])


print("Start training")


def getPrecision(pred_test, yTest, targetLabel):
    #Precision for non-vague
    targetLabelCount = 0
    correctTargetLabelCount = 0
    
    for idx in range(len(pred_test)):
        if pred_test[idx] == targetLabel:
            targetLabelCount += 1
            
            if pred_test[idx] == yTest[idx]:
                correctTargetLabelCount += 1
    
    if correctTargetLabelCount == 0:
        return 0
    
    return float(correctTargetLabelCount) / targetLabelCount

def predict_classes(prediction):
    return prediction.argmax(axis=-1)

for epoch in range(nb_epoch):       
    train(epoch)
    test()
    print("Max accuracy: %.4f\n" % max_acc)
