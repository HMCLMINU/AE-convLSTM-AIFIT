#!/usr/bin/env python3

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import hickle as hkl
import numpy as np
import random 
import json
np.random.seed(9 ** 10)
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras import backend as K
from tensorflow.keras import regularizers
from tensorflow.keras.models import Sequential
from tensorflow.keras.utils import plot_model
from tensorflow.keras.initializers import RandomNormal
from tensorflow.keras.callbacks import LearningRateScheduler
from tensorflow.keras.callbacks import TensorBoard
from tensorflow.keras.datasets import mnist
from config import * 
from sys import stdout

import argparse
import math
import cv2 as cv
import os, glob
import numpy as np
import matplotlib.pyplot as plt
from tensorflow.keras.optimizers import Adam
from custom_layers import AttnLossLayer

tf.random.set_seed(0)

OPTIM_A = Adam(lr=0.001, beta_1=0.5)
FRAME_LENGTH = 1
FOR_NEW_DATA_LOAD = 1
Training = 0.7
Validation = 0.2
Test = 0.3

time = 4
height, width = 336, 336
color_channels = 3

it = int(10/10)

epochs = 1000

batch_size = 14
number_of_hiddenunits = 32

_data = os.listdir(data_save_path)
random.shuffle(_data)
num_of_train = int(len(_data) * 0.7) 
num_of_val = int(len(_data) * 0.2) 
num_of_test = int(len(_data) - num_of_train - num_of_val) 

tensorboard_save_folder = '/home/hmcl/AE-convLSTM/AE-convLSTM_AIFIT/tensorboard'
checkpoint_path = '/home/hmcl/AE-convLSTM/AE-convLSTM_AIFIT/checkpoint'
model_save_folder = '/home/hmcl/AE-convLSTM/AE-convLSTM_AIFIT/model_save/'
img_save_folder = '/home/hmcl/AE-convLSTM/AE-convLSTM_AIFIT/image/'

cp_callback = tf.keras.callbacks.ModelCheckpoint(filepath=checkpoint_path, verbose=1, save_best_only=True,
                                                 save_weights_only=False,period=100)
tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=tensorboard_save_folder, histogram_freq=0, write_graph=True,
                                                      write_images=False)
early_stopping = tf.keras.callbacks.EarlyStopping()
        
options = tf.data.Options()
options.experimental_distribute.auto_shard_policy = tf.data.experimental.AutoShardPolicy.OFF

def batch_dispatch(mode):
    train_data = _data[:num_of_train]
    val_data = _data[num_of_train:num_of_train+num_of_val]
    random.shuffle(train_data)
    random.shuffle(val_data)
    if mode == "train":
        counter = 0
        while counter<=num_of_train:
            image_seqs = np.empty((0,time,height,width,color_channels))
            labels = np.empty((0,time, height,width,color_channels))  
            for i in range(it):          
                np_data = np.load(os.path.join(data_save_path, train_data[counter]), allow_pickle=True)
                if len(np_data['arr_0']) == 0:
                    continue

                for j in range(np_data['arr_0'].shape[0] - 2*time+1):
                    t = np_data['arr_0'][j:j+time, :, :, :].reshape(1, time,height,width,color_channels)
                    t_label = np_data['arr_0'][j + time:j+time*2, :, :, :].reshape(1, time, height , width, color_channels)
                    image_seqs = np.vstack((image_seqs, t/255))
                    labels = np.vstack((labels, t_label/255))
                counter += 1
                if counter>=num_of_train:
                    counter = 0
                    random.shuffle(train_data)
            # train_data = tf.data.Dataset.from_tensor_slices((image_seqs, labels)) 
            # train_data = train_data.batch(batch_size)
            # train_data = train_data.with_options(options)
            # yield train_data  
            yield image_seqs, labels
    elif mode == "val":
        counter = 0
        while counter<=num_of_val:
            val_image_seqs = np.empty((0,time,height,width,color_channels))
            val_labels = np.empty((0,time, height,width,color_channels))
            for i in range(it):
                np_data = np.load(os.path.join(data_save_path, val_data[counter]), allow_pickle=True)
                if len(np_data['arr_0']) == 0:
                    continue

                for j in range(np_data['arr_0'].shape[0] - 2*time+1):
                    t = np_data['arr_0'][j:j+time, :, :, :].reshape(1, time,height,width,color_channels)
                    t_label = np_data['arr_0'][j + time:j+time*2, :, :, :].reshape(1, time, height , width, color_channels)
                    val_image_seqs = np.vstack((val_image_seqs, t/255))
                    val_labels = np.vstack((val_labels, t_label/255))
                            
                counter += 1
                if counter>=num_of_val:
                    counter = 0
                    random.shuffle(val_data)
            # val_data = tf.data.Dataset.from_tensor_slices((val_image_seqs, val_labels)) 
            # val_data = val_data.batch(batch_size)
            # val_data = val_data.with_options(options)

            # yield val_data
            yield val_image_seqs, val_labels

def test_batch(): 
    test_data = _data[num_of_train + num_of_val:]
    random.shuffle(test_data)
    counter = 0
    image_seqs = np.empty((0,time,height,width,color_channels))
    labels = np.empty((0,time, height,width,color_channels)) 
    while counter<num_of_test:    
        np_data = np.load(os.path.join(data_save_path, test_data[counter]), allow_pickle=True)
        if len(np_data['arr_0']) == 0:
            continue

        for j in range(np_data['arr_0'].shape[0] - 2*time+1):
            t = np_data['arr_0'][j:j+time, :, :, :].reshape(1, time,height,width,color_channels)
            t_label = np_data['arr_0'][j + time:j+time*2, :, :, :].reshape(1, time, height , width, color_channels)
            image_seqs = np.vstack((image_seqs, t/255.))
            labels = np.vstack((labels, t_label/255.))
        counter += 1
        if counter>=num_of_train:
            counter = 0
            random.shuffle(test_data)
    return image_seqs, labels

def cross_entropy_loss(y_true, y_pred):
    x = -K.mean(y_true * K.log(y_pred) + (1 - y_true)*K.log(1-y_pred))
    return x

def get_model():
    # input_img = keras.Input(shape=(time,height,width,color_channels))
    seq = Sequential()

    seq.add(layers.TimeDistributed(layers.Conv2D(256, (5, 5), activation = 'relu', strides=2, padding="same"), batch_input_shape=(None, time, height, width, color_channels)))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    # seq.add(layers.TimeDistributed(layers.Conv2D(, (5, 5), activation = 'relu', strides=2, padding="same")))
    # seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(240, (5, 5), activation = 'relu', strides=2, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(230, (5, 5), activation = 'relu', strides=2, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(220, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(210, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(200, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(190, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(180, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))
    
    seq.add(layers.TimeDistributed(layers.Conv2D(170, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))
    
    seq.add(layers.TimeDistributed(layers.Conv2D(160, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(128, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))
    # # # # #
    seq.add(layers.ConvLSTM2D(64, (3, 3), padding="same", return_sequences=True)) # temporal encoder
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))
    seq.add(layers.ConvLSTM2D(32, (3, 3), padding="same", return_sequences=True)) # bottleneck
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))
    seq.add(layers.ConvLSTM2D(64, (3, 3), padding="same", return_sequences=True)) # temporal decoder
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))
    # # # # #

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(128, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(160, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(170, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(180, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(190, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(200, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(210, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(220, (5, 5), activation = 'relu', strides=1, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(230, (5, 5), activation = 'relu', strides=2, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(240, (5, 5), activation = 'relu', strides=2, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2DTranspose(256, (5, 5), activation = 'relu', strides=2, padding="same")))
    seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    # seq.add(layers.TimeDistributed(layers.Conv2DTranspose(512, (5, 5), activation = 'relu', strides=2, padding="same")))
    # seq.add(layers.TimeDistributed(layers.LayerNormalization()))

    seq.add(layers.TimeDistributed(layers.Conv2D(3, (5, 5), activation="sigmoid", padding="same")))
    # seq.add(layers.Conv2D(3, (11, 11), activation="sigmoid", padding="same"))
    seq.summary()
    seq.compile(loss='mse', optimizer=keras.optimizers.Adam(lr=1e-4, decay=1e-5, epsilon=1e-6))
    # seq.compile(loss='binary_crossentropy', optimizer=keras.optimizers.Adam(lr=1e-4, decay=1e-5, epsilon=1e-6))
    return seq

def new_train():
    print ("Creating models...")

    autoencoder = get_model()

    history = autoencoder.fit(batch_dispatch(mode = "train"),
                    epochs=epochs,
                    steps_per_epoch = num_of_train*7//batch_size,
                    batch_size= batch_size,
                    validation_data = batch_dispatch(mode = "val"),
                    validation_steps=1,
                    callbacks=[cp_callback, tensorboard_callback])
    # with open(os.path.join(base_folder,'files',model_name,'training_logs.json'),'w') as w:
    #     json.dump(history.history,w)
    autoencoder.save(model_save_folder + 'autoencoder_v5.h5')
     

def predict():
    # # # Load Model
    # autoencoder = tf.keras.models.load_model(model_save_folder + 'autoencoder_v5.h5')
    autoencoder = tf.keras.models.load_model(checkpoint_path)
    test_x, test_y = test_batch()
    test_x = test_x.astype('float32')
    test_y = test_y.astype('float32')
    # Prediction ...
    predicted_ = np.empty((0, height, width , color_channels)) 
    test_image_seqs = np.empty((0,height,width,color_channels))
    # for i in range(int(test_x.shape[0]/num_of_test)):
    #     #predict until 10 frames
    #     if i%7 == 0:
    #         predicted_frames = autoencoder.predict(test_x[i].reshape(1, time, height, width, color_channels)) # (1, 4, h, w, c)        
    #         predicted_ = np.vstack((predicted_, predicted_frames.reshape(4, 336, 336, 3)))
    #     else:
    #         predicted_frames = autoencoder.predict(predicted_frames)
    #         # if i%6 == 0: # last frame
    #         #     predicted_frames = predicted_frames[:2] # two image
    #         predicted_ = np.vstack((predicted_, predicted_frames.reshape(4, 336, 336, 3)))
        
    #         if predicted_.shape[0] >= 10:
    #             predicted_ = predicted_[:10]
    #             break
    sim = 0
    n = 10
    while (predicted_.shape[0]<num_of_test*10):
        for i in range(3):
            if i == 0:
                predicted_frames = autoencoder.predict(test_x[sim].reshape(1, time, height, width, color_channels)) # (1, 4, h, w, c)        
                predicted_ = np.vstack((predicted_, predicted_frames.reshape(4, 336, 336, 3)))
            else:
                predicted_frames = autoencoder.predict(predicted_frames)
                predicted_ = np.vstack((predicted_, predicted_frames.reshape(4, 336, 336, 3)))
                if i == 2:
                    predicted_ = predicted_[:predicted_.shape[0]-2]
        sim = sim+7
 
    # plt.imshow(predicted_frames[0]
    # plot original label
    for i in range(int(test_y.shape[0])):
        if i % 7 == 6:
            img = test_y[i] # all image at last batch
            test_image_seqs = np.vstack((test_image_seqs, img))
        else:
            img = test_y[i][0].reshape(1, height, width, color_channels) # first image at each batch
            test_image_seqs = np.vstack((test_image_seqs, img))

    for sim in range(int(predicted_.shape[0]/n)):
        plt.figure(figsize=(n*2, 5))
        plt.rcParams["figure.figsize"] = (5, 5)
        start = sim*10
        for i in range(1, n + 1):
            # Display original
            plt.suptitle('Batch' + str(sim) + 'True label vs Predicted label',fontweight="bold")
            ax = plt.subplot(2, n, i)
            ax.set_title("Time at :" + str(i+4))
            plt.imshow(test_image_seqs[start+i-1])
            plt.gray()
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)

            # Display reconstruction
            ax = plt.subplot(2, n, i + n)
            ax.set_title("Time at :" + str(i+4))
            plt.imshow(predicted_[start+i-1])
            plt.gray()
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)
        # plt.show()
        my_file = 'batch_'+str(sim) + 'th_result.png'
        plt.savefig(os.path.join(img_save_folder, my_file))
    
    print("~~~~~~~~PREDICTION DONE~~~~~~~~~~~")

if __name__ == "__main__":
    gpus = tf.config.experimental.list_physical_devices('GPU')
    if gpus:
        try:
            # Currently, memory growth needs to be the same across GPUs
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            logical_gpus = tf.config.experimental.list_logical_devices('GPU')
            print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
        except RuntimeError as e:
            # Memory growth must be set before GPUs have been initialized
            print(e)

    # Use Multi GPU
    # strategy = tf.distribute.MirroredStrategy()
    communication_options = tf.distribute.experimental.CommunicationOptions(
    implementation=tf.distribute.experimental.CommunicationImplementation.NCCL)
    strategy = tf.distribute.MultiWorkerMirroredStrategy(communication_options=communication_options)
    with strategy.scope():
        # get_model()        
        # new_train()
        predict()
