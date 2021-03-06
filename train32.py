import numpy as np
import matplotlib.pyplot as plt

import sys

from math import *

import torch
import torch.nn as nn
from torch.nn import Parameter
from torch.nn import functional as F
import torch.optim
from torch.autograd import Variable

import time
import copy

from architecture import ClassifierGenerator, NetworkSKL, tovar, toivar, normalizeAndProject
from problem import problemGenerator
from testing import evalClassifier, compareMethodsOnSet

def trainingStep(net, NTRAIN, min_difficulty = 1.0, max_difficulty = 1.0, min_sparseness = 0, max_sparseness = 0, min_imbalance = 0, max_imbalance = 0, feature_variation = True, class_variation = True, BS = 200):
	FEATURES = net.FEATURES
	CLASSES = net.CLASSES
	
	net.zero_grad()
	batch_mem = []
	batch_test = []
	batch_label = []
	class_count = []
	
	for i in range(BS):
		if feature_variation:
			feat = np.random.randint(2.5*FEATURES) + FEATURES//2
		else:
			feat = FEATURES
		
		if class_variation:
			classes = np.random.randint(CLASSES-2) + 2
		else:
			classes = CLASSES
			
		xd,yd = problemGenerator(N=NTRAIN+100, FEATURES=feat, CLASSES=classes, 
								 sigma = np.random.rand()*(max_difficulty - min_difficulty) + min_difficulty,
								 sparseness = np.random.rand()*(max_sparseness - min_sparseness) + min_sparseness,
								 imbalance = np.random.rand()*(max_imbalance - min_imbalance) + min_imbalance)
		
		if classes<CLASSES:
			yd = np.pad(yd, ( (0,0), (0,CLASSES-classes)), 'constant', constant_values=0)
		xd = normalizeAndProject(xd, NTRAIN, FEATURES)
		
		trainset = np.hstack([xd[0:NTRAIN],yd[0:NTRAIN]])
		testset = xd[NTRAIN:]
		labelset = yd[NTRAIN:]

		batch_mem.append(trainset)
		batch_test.append(testset)
		batch_label.append(labelset)
		class_count.append(classes)

	batch_mem = tovar(np.array(batch_mem).transpose(0,2,1).reshape(BS,1,FEATURES+CLASSES,NTRAIN))
	batch_test = tovar(np.array(batch_test).transpose(0,2,1).reshape(BS,1,FEATURES,100))
	batch_label = tovar(np.array(batch_label).transpose(0,2,1))
	class_count = torch.cuda.FloatTensor(np.array(class_count))
	
	net.zero_grad()
	p = net.forward(batch_mem, batch_test, class_count)
	loss = -torch.sum(p*batch_label,1).mean()
	loss.backward()
	net.adam.step()
	err = loss.cpu().data.numpy()[0]
	
	return err
	
# Echocardiogram, blood transfusion, autism
echocardio = np.load("data/echocardiogram.npz")
bloodtransfusion = np.load("data/bloodtransfusion.npz")
autism = np.load("data/autism.npz")
	
net = ClassifierGenerator(FEATURES=32, CLASSES=16, NETSIZE=384).cuda()

difficulty_level = 0.0125
errs = []

err = 0
err_count = 0

for i in range(100000):	
	err += trainingStep(net, 100, min_difficulty = difficulty_level * 0.5, max_difficulty = difficulty_level * 1.5)
	err_count += 1
	
	if i%10000 == 5000:
		torch.save(net.state_dict(),open("ckpt/classifier-generator-32-16-ckpt%d.pth" % i,"wb"))
		
	if err_count >= 50:
		err = err/err_count
		errs.append(err)
		
		methods = [lambda: NetworkSKL(net)]
		results1 = compareMethodsOnSet(methods, echocardio['x'], echocardio['y'].astype(np.int32), samples=200)
		auc1 = results1[0][1]
		results2 = compareMethodsOnSet(methods, bloodtransfusion['x'], bloodtransfusion['y'].astype(np.int32), samples=200)
		auc2 = results2[0][1]
		results3 = compareMethodsOnSet(methods, autism['x'], autism['y'].astype(np.int32), samples=200)
		auc3 = results3[0][1]
		
		f = open("training_curves/training32-16.txt","a")
		f.write("%d %.6g %.6g %.6g %.6g %.6g\n" % (i, err, difficulty_level, auc1, auc2, auc3))
		f.close()
	
		# Curriculum
		if err<0.7 and difficulty_level<0.4:
			difficulty_level *= 2.0
		
		err = 0
		err_count = 0
		
		torch.save(net.state_dict(),open("models/classifier-generator-32-16.pth","wb"))
