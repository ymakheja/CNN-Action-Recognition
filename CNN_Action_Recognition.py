
# coding: utf-8

# # Training a ConvNet PyTorch
# 
# In this notebook, you'll learn how to use the powerful PyTorch framework to specify a conv net architecture and train it on the human action recognition dataset. 
# 

# In[1]:


import torch
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable
from torch.utils.data import DataLoader,sampler,Dataset
import torchvision.datasets as dset
import torchvision.transforms as T
import timeit
from PIL import Image
import os
import numpy as np
import scipy.io


# ## What's this PyTorch business?
# 
# * When using a framework like PyTorch or TensorFlow you can harness the power of the GPU for your own custom neural network architectures without having to write CUDA code directly.
# * this notebook will walk you through much of what you need to do to train models using pytorch. if you want to learn more or need further clarification on topics that aren't fully explained here, here are 2 good Pytorch tutorials. 1): http://pytorch.org/tutorials/beginner/deep_learning_60min_blitz.html 2)http://pytorch.org/tutorials/beginner/pytorch_with_examples.html
# * It's not necessary to have a GPU for this homework, using a GPU can make your code run faster.
# 

# ## Load Datasets
# 
# In this part, we will load the action recognition dataset for the neural network. In order to load data from our custom dataset, we need to write a custom Dataloader. If you put hw6_data.mat, /valClips,/trainClips,/testClips under the folder of ./data/ , you do not need to change anything in this part.

# First, load the labels of the dataset, you should write your path of the hw6_data.mat file.

# In[2]:


label_mat=scipy.io.loadmat('../input/dataset/hw6_data.mat')
label_train=label_mat['trLb']
print(len(label_train))
label_val=label_mat['valLb']
print(len(label_val))


# ### Dataset class
# 
# torch.utils.data.Dataset is an abstract class representing a dataset. The custom dataset should inherit Dataset and override the following methods:
# 
#     __len__ so that len(dataset) returns the size of the dataset.
#     __getitem__ to support the indexing such that dataset[i] can be used to get ith sample
# 
# Let’s create a dataset class for our action recognition dataset. We will read images in __getitem__. This is memory efficient because all the images are not stored in the memory at once but read as required.
# 
# Sample of our dataset will be a dict {'image':image,'img_path':img_path,'Label':Label}. Our datset will take an optional argument transform so that any required processing can be applied on the sample. 

# In[3]:



class ActionDataset(Dataset):
    """Action dataset."""

    def __init__(self,  root_dir,labels=[], transform=None):
        """
        Args:
            root_dir (string): Directory with all the images.
            labels(list): labels if images.
            transform (callable, optional): Optional transform to be applied on a sample.
        """
        self.root_dir = root_dir
        self.transform = transform
        self.length=len(os.listdir(self.root_dir))
        self.labels=labels
    def __len__(self):
        return self.length*3

    def __getitem__(self, idx):
        
        folder=int(idx/3)+1
        imidx=idx%3+1
        folder=format(folder,'05d')
        imgname=str(imidx)+'.jpg'
        img_path = os.path.join(self.root_dir,
                                folder,imgname)
        image = Image.open(img_path)
        if len(self.labels)!=0:
            Label=self.labels[int(idx/3)][0]-1
        if self.transform:
            image = self.transform(image)
        if len(self.labels)!=0:
            sample={'image':image,'img_path':img_path,'Label':Label}
        else:
            sample={'image':image,'img_path':img_path}
        return sample
  


# Iterating over the dataset by a for loop.

# In[4]:


image_dataset=ActionDataset(root_dir='../input/cse512f18hw6vid/data/data/trainClips/',                            labels=label_train,transform=T.ToTensor())

#iterating though the dataset
for i in range(10):
    sample=image_dataset[i]
    print(sample['image'].shape)
    print(sample['Label'])
    print(sample['img_path'])
     
   


# We can iterate over the created dataset with a 'for' loop as before. However, we are losing a lot of features by using a simple for loop to iterate over the data. In particular, we are missing out on:
# 
# * Batching the data
# * Shuffling the data
# * Load the data in parallel using multiprocessing workers.
# 
# torch.utils.data.DataLoader is an iterator which provides all these features. 

# In[5]:


image_dataloader = DataLoader(image_dataset, batch_size=4,
                        shuffle=True, num_workers=0)


for i,sample in enumerate(image_dataloader):
    sample['image']=sample['image']
    print(i,sample['image'].shape,sample['img_path'],sample['Label'])
    if i>20: 
        break


# Dataloaders for the training, validationg and testing set. 

# In[6]:


image_dataset_train=ActionDataset(root_dir='../input/cse512f18hw6vid/data/data/trainClips/',labels=label_train,transform=T.ToTensor())

image_dataloader_train = DataLoader(image_dataset_train, batch_size=32,
                        shuffle=True, num_workers=0)
image_dataset_val=ActionDataset(root_dir='../input/cse512f18hw6vid/data/data/valClips/',labels=label_val,transform=T.ToTensor())

image_dataloader_val = DataLoader(image_dataset_val, batch_size=32,
                        shuffle=False, num_workers=0)
image_dataset_test=ActionDataset(root_dir='../input/cse512f18hw6vid/data/data/testClips/',labels=[],transform=T.ToTensor())

image_dataloader_test = DataLoader(image_dataset_test, batch_size=32,
                        shuffle=False, num_workers=0)


# In[7]:


dtype = torch.FloatTensor # the CPU datatype
# Constant to control how frequently we print train loss
print_every = 100
# This is a little utility that we'll use to reset the model
# if we want to re-initialize all our parameters
def reset(m):
    if hasattr(m, 'reset_parameters'):
        m.reset_parameters()


# ## Example Model
# 
# ### Some assorted tidbits
# 
# Let's start by looking at a simple model. First, note that PyTorch operates on Tensors, which are n-dimensional arrays functionally analogous to numpy's ndarrays, with the additional feature that they can be used for computations on GPUs.
# 
# We'll provide you with a Flatten function, which we explain here. Remember that our image data (and more relevantly, our intermediate feature maps) are initially N x C x H x W, where:
# * N is the number of datapoints
# * C is the number of image channels. 
# * H is the height of the intermediate feature map in pixels
# * W is the height of the intermediate feature map in pixels
# 
# This is the right way to represent the data when we are doing something like a 2D convolution, that needs spatial understanding of where the intermediate features are relative to each other. When we input  data into fully connected affine layers, however, we want each datapoint to be represented by a single vector -- it's no longer useful to segregate the different channels, rows, and columns of the data. So, we use a "Flatten" operation to collapse the C x H x W values per representation into a single long vector. The Flatten function below first reads in the N, C, H, and W values from a given batch of data, and then returns a "view" of that data. "View" is analogous to numpy's "reshape" method: it reshapes x's dimensions to be N x ??, where ?? is allowed to be anything (in this case, it will be C x H x W, but we don't need to specify that explicitly). 

# In[8]:


class Flatten(nn.Module):
    def forward(self, x):
        N, C, H, W = x.size() # read in N, C, H, W
        return x.view(N, -1)  # "flatten" the C * H * W values into a single vector per image


# ### The example model itself
# 
# The first step to training your own model is defining its architecture.
# 
# Here's an example of a convolutional neural network defined in PyTorch -- try to understand what each line is doing, remembering that each layer is composed upon the previous layer. We haven't trained anything yet - that'll come next - for now, we want you to understand how everything gets set up.  nn.Sequential is a container which applies each layer
# one after the other.
# 
# In this example, you see 2D convolutional layers (Conv2d), ReLU activations, and fully-connected layers (Linear). You also see the Cross-Entropy loss function, and the Adam optimizer being used. 
# 
# Make sure you understand why the parameters of the Linear layer are 10092 and 10.
# 

# In[9]:


# Here's where we define the architecture of the model... 
simple_model = nn.Sequential(
                nn.Conv2d(3, 32, kernel_size=7, stride=2),
                nn.ReLU(inplace=True),
                Flatten(), # see above for explanation
                nn.Linear(10092, 10), # affine layer
              )

# Set the type of all data in this model to be FloatTensor 
simple_model.type(dtype)

loss_fn = nn.CrossEntropyLoss().type(dtype)
optimizer = optim.Adam(simple_model.parameters(), lr=1e-2) # lr sets the learning rate of the optimizer


# PyTorch supports many other layer types, loss functions, and optimizers - you will experiment with these next. Here's the official API documentation for these (if any of the parameters used above were unclear, this resource will also be helpful). 
# 
# * Layers: http://pytorch.org/docs/nn.html
# * Activations: http://pytorch.org/docs/nn.html#non-linear-activations
# * Loss functions: http://pytorch.org/docs/nn.html#loss-functions
# * Optimizers: http://pytorch.org/docs/optim.html#algorithms

# ## Training a specific model
# 
# In this section, we're going to specify a model for you to construct. The goal here isn't to get good performance (that'll be next), but instead to get comfortable with understanding the PyTorch documentation and configuring your own model. 
# 
# Using the code provided above as guidance, and using the following PyTorch documentation, specify a model with the following architecture:
# 
# * 7x7 Convolutional Layer with 8 filters and stride of 1
# * ReLU Activation Layer
# * 2x2 Max Pooling layer with a stride of 2
# * 7x7 Convolutional Layer with 16 filters and stride of 1
# * ReLU Activation Layer
# * 2x2 Max Pooling layer with a stride of 2
# * Flatten the feature map
# * ReLU Activation Layer
# * Affine layer to map input units to 10 outputs, you need to figure out the input size here.
# 

# In[10]:


fixed_model_base = nn.Sequential( 
    #########1st TODO  (10 points)###################
    nn.Conv2d(3,8,kernel_size=7,stride=1),
    nn.ReLU(inplace=True),
    nn.MaxPool2d(2, stride = 2),
    nn.Conv2d(8,16,kernel_size=7,stride=1),
    nn.ReLU(inplace=True),
    nn.MaxPool2d(2,stride=2),
    Flatten(),
    nn.ReLU(inplace=True),
    nn.Linear(1936,10)
    ####################################
            )
fixed_model = fixed_model_base.type(dtype)



# To make sure you're doing the right thing, use the following tool to check the dimensionality of your output (it should be 32 x 10, since our batches have size 32 and the output of the final affine layer should be 10, corresponding to our 10 classes):

# In[11]:


## Now we're going to feed a random batch into the model you defined and make sure the output is the right size
x = torch.randn(32, 3, 64, 64).type(dtype)
x_var = Variable(x.type(dtype)) # Construct a PyTorch Variable out of your input data
ans = fixed_model(x_var)        # Feed it through the model! 

# Check to make sure what comes out of your model
# is the right dimensionality... this should be True
# if you've done everything correctly
print(np.array(ans.size()))
np.array_equal(np.array(ans.size()), np.array([32, 10]))   


# ### Train the model.
# 
# Now that you've seen how to define a model and do a single forward pass of some data through it, let's  walk through how you'd actually train one whole epoch over your training data (using the fixed_model_base we provided above).
# 
# Make sure you understand how each PyTorch function used below corresponds to what you implemented in your custom neural network implementation.
# 
# Note that because we are not resetting the weights anywhere below, if you run the cell multiple times, you are effectively training multiple epochs (so your performance should improve).
# 
# First, set up an RMSprop optimizer (using a 1e-4 learning rate) and a cross-entropy loss function:

# In[12]:


################ 2nd TODO  (5 points)##################
optimizer = torch.optim.RMSprop(fixed_model_base.parameters(), lr = 1e-4)
loss_fn = nn.CrossEntropyLoss()


# In[13]:


# This sets the model in "training" mode. 
# This is relevant for some layers that may have different behavior
# in training mode vs testing mode, such as Dropout and BatchNorm. 
fixed_model.train()

# Load one batch at a time.
for t, sample in enumerate(image_dataloader_train):
    x_var = Variable(sample['image'])
    #print(type(x_var.data))
    #print(x_var.shape)
    y_var = Variable(sample['Label']).long()

    # This is the forward pass: predict the scores for each class, for each x in the batch.
    scores = fixed_model(x_var)
    
    # Use the correct y values and the predicted y values to compute the loss.
    loss = loss_fn(scores, y_var)
    
    if (t + 1) % print_every == 0:
        print('t = %d, loss = %.4f' % (t + 1, loss.data[0]))

    # Zero out all of the gradients for the variables which the optimizer will update.
    optimizer.zero_grad()
    
    # This is the backwards pass: compute the gradient of the loss with respect to each 
    # parameter of the model.
    loss.backward()
    
    # Actually update the parameters of the model using the gradients computed by the backwards pass.
    optimizer.step()
   


# Now you've seen how the training process works in PyTorch. To save you writing boilerplate code, we're providing the following helper functions to help you train for multiple epochs and check the accuracy of your model:

# In[14]:


def train(model, loss_fn, optimizer, dataloader, num_epochs = 1):
    for epoch in range(num_epochs):
        print('Starting epoch %d / %d' % (epoch + 1, num_epochs))
        model.train()
        for t, sample in enumerate(dataloader):
            x_var = Variable(sample['image'])
            y_var = Variable(sample['Label'].long())

            scores = model(x_var)
            
            loss = loss_fn(scores, y_var)
            if (t + 1) % print_every == 0:
                print('t = %d, loss = %.4f' % (t + 1, loss.data[0]))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

def check_accuracy(model, loader):
    '''
    if loader.dataset.train:
        print('Checking accuracy on validation set')
    else:
        print('Checking accuracy on test set')  
    '''
    num_correct = 0
    num_samples = 0
    model.eval() # Put the model in test mode (the opposite of model.train(), essentially)
    for t, sample in enumerate(loader):
        x_var = Variable(sample['image'])
        y_var = sample['Label']
        #y_var=y_var.cpu()
        scores = model(x_var)
        _, preds = scores.data.max(1)#scores.data.cpu().max(1)
        #print(preds)
        #print(y_var)
        num_correct += (preds.numpy() == y_var.numpy()).sum()
        num_samples += preds.size(0)
    acc = float(num_correct) / num_samples
    print('Got %d / %d correct (%.2f)' % (num_correct, num_samples, 100 * acc))
    
    



# ### Check the accuracy of the model.
# 
# Let's see the train and check_accuracy code in action -- feel free to use these methods when evaluating the models you develop below.
# 
# You should get a training loss of around 1.0-1.2, and a validation accuracy of around 50-60%. As mentioned above, if you re-run the cells, you'll be training more epochs, so your performance will improve past these numbers.
# 
# But don't worry about getting these numbers better -- this was just practice before you tackle designing your own model.

# In[15]:


torch.random.manual_seed(12345)
fixed_model.cpu()
fixed_model.apply(reset) 
fixed_model.train() 
train(fixed_model, loss_fn, optimizer,image_dataloader_train, num_epochs=1) 
check_accuracy(fixed_model, image_dataloader_train)# check accuracy on the training set


# ### Don't forget the validation set!
# 
# And note that you can use the check_accuracy function to evaluate on the validation set, by passing **image_dataloader_val** as the second argument to check_accuracy. The accuracy on validation set is arround 40-50%.

# In[16]:


check_accuracy(fixed_model, image_dataloader_val)#check accuracy on the validation set


# ##### Train a better  model for action recognition!
# 
# Now it's your job to experiment with architectures, hyperparameters, loss functions, and optimizers to train a model that achieves better accuracy on the action recognition **validation** set. You can use the check_accuracy and train functions from above.

# ### Things you should try:
# - **Filter size**: Above we used 7x7; this makes pretty pictures but smaller filters may be more efficient
# - **Number of filters**: Do more or fewer do better?
# - **Pooling vs Strided Convolution**: Do you use max pooling or just stride convolutions?
# - **Batch normalization**: Try adding spatial batch normalization after convolution layers and vanilla batch normalization after affine layers. Do your networks train faster?
# - **Network architecture**: The network above has two layers of trainable parameters. Can you do better with a deep network? Good architectures to try include:
#     - [conv-relu-pool]xN -> [affine]xM -> [softmax or SVM]
#     - [conv-relu-conv-relu-pool]xN -> [affine]xM -> [softmax or SVM]
#     - [batchnorm-relu-conv]xN -> [affine]xM -> [softmax or SVM]
# - **Global Average Pooling**: Instead of flattening and then having multiple affine layers, perform convolutions until your image gets small (7x7 or so) and then perform an average pooling operation to get to a 1x1 image picture (1, 1 , Filter#), which is then reshaped into a (Filter#) vector. This is used in [Google's Inception Network](https://arxiv.org/abs/1512.00567) (See Table 1 for their architecture).
# - **Regularization**: Add l2 weight regularization, or perhaps use Dropout.
# 
# ### Tips for training
# For each network architecture that you try, you should tune the learning rate and regularization strength. When doing this there are a couple important things to keep in mind:
# 
# - If the parameters are working well, you should see improvement within a few hundred iterations
# - Remember the coarse-to-fine approach for hyperparameter tuning: start by testing a large range of hyperparameters for just a few training iterations to find the combinations of parameters that are working at all.
# - Once you have found some sets of parameters that seem to work, search more finely around these parameters. You may need to train for more epochs.
# - You should use the validation set for hyperparameter search, and save your test set for evaluating your architecture on the best parameters as selected by the validation set.
# 
# ### Going above and beyond
# If you are feeling adventurous there are many other features you can implement to try and improve your performance. You are **not required** to implement any of these; however they would be good things to try.
# 
# - Alternative update steps: For the assignment we implemented SGD+momentum, RMSprop, and Adam; you could try alternatives like AdaGrad or AdaDelta.
# - Alternative activation functions such as leaky ReLU, parametric ReLU, ELU, or MaxOut.
# - Model ensembles
# - Data augmentation
# - New Architectures
#   - [ResNets](https://arxiv.org/abs/1512.03385) where the input from the previous layer is added to the output.
#   - [DenseNets](https://arxiv.org/abs/1608.06993) where inputs into previous layers are concatenated together.
#   - [This blog has an in-depth overview](https://chatbotslife.com/resnets-highwaynets-and-densenets-oh-my-9bb15918ee32)
# 
# If you do decide to implement something extra, clearly describe it in the "Extra Credit Description" cell below.
# 
# ### What we expect
# At the very least, you should be able to train a ConvNet that gets at least 55% accuracy on the validation set. This is just a lower bound - if you are careful it should be possible to get accuracies much higher than that! Extra credit points will be awarded for particularly high-scoring models or unique approaches.
# 
# You should use the space below to experiment and train your network. 
# 
# 

# In[40]:


###########3rd TODO (20 points, must submit the results to Kaggle) ##############
# Train your model here, and make sure the output of this cell is the accuracy of your best model on the 
# train, val, and test sets. Here's some code to get you started. The output of this cell should be the training
# and validation accuracy on your best model (measured by validation accuracy).
fixed_model_base = nn.Sequential( 
    nn.Conv2d(3,128,kernel_size=3,stride=1),
    nn.ReLU(inplace=True),
    nn.BatchNorm2d(128),
    
    nn.Conv2d(128,128,kernel_size=3,stride=1),
    nn.ReLU(inplace=True),
    nn.BatchNorm2d(128),
    nn.MaxPool2d(2, stride = 2),

    
    nn.Conv2d(128,256,kernel_size=3,stride=1),
    nn.ReLU(inplace=True),
    nn.BatchNorm2d(256),
    
    nn.Conv2d(256,256,kernel_size=3,stride=1),
    nn.ReLU(inplace=True),
    nn.BatchNorm2d(256),
    nn.MaxPool2d(2,stride=2),

    Flatten(),
    nn.Linear(43264,10),
    nn.LogSoftmax()
)
# model = None
optimizer = torch.optim.Adadelta(fixed_model_base.parameters(), lr = 0.0001)
loss_fn = nn.CrossEntropyLoss()

fixed_model = fixed_model_base.type(dtype)
torch.random.manual_seed(12345)
fixed_model.cpu()
fixed_model.apply(reset) 
fixed_model.train() 
train(fixed_model_base, loss_fn, optimizer,image_dataloader_train, num_epochs=1) 
check_accuracy(fixed_model, image_dataloader_val)


# ### Describe what you did 
# 
# In the cell below you should write an explanation of what you did, any additional features that you implemented, and any visualizations or graphs that you make in the process of training and evaluating your network.

# Tell us here!
# **###########4th TODO (5 points) ##############**
# 
# *  3*3 Convolution layer with 128 filters and stride 1
# * ReLU Activation Layer
# * Batch normalization layer
# * 3*3 Convolutional Layer with 128 filters and stride of 1
# * ReLU Activation Layer
# * Batch normalization layer
# * 2x2 Max Pooling layer with a stride of 2
# * 3*3 Convolutional Layer with 256 filters and stride of 1
# * ReLU Activation Layer
# * Batch normalization layer
# * 3*3 Convolutional Layer with 256 filters and stride of 1
# * ReLU Activation Layer
# * Batch normalization layer
# * 2x2 Max Pooling layer with a stride of 2
# * Flatten the feature map
# * Affine layer to map input units to 10 outputs
# * LogSoftmax layer
# 
# 
# 

# ### Testing the model and submit on Kaggle
# Testing the model on the testing set and save the results as a .csv file. 
# Please submitted the results.csv file generated by predict_on_test() to Kaggle(https://www.kaggle.com/c/cse512springhw3) to see how well your network performs on the test set. 
# #######5th TODO (submit the result to Kaggle, the highest 3 entries get extra 10 points )###############

# In[ ]:


def predict_on_test(model, loader):
    '''
    if loader.dataset.train:
        print('Checking accuracy on validation set')
    else:
        print('Checking accuracy on test set')  
    '''
    num_correct = 0
    num_samples = 0
    model.eval() # Put the model in test mode (the opposite of model.train(), essentially)
    results=open('results.csv','w')
    count=0
    results.write('Id'+','+'Class'+'\n')
    for t, sample in enumerate(loader):
        x_var = Variable(sample['image'])
        scores = model(x_var)
        _, preds = scores.data.max(1)
        for i in range(len(preds)):
            results.write(str(count)+','+str(preds[i].item())+'\n')
            count+=1
    results.close()
    return count
    
count=predict_on_test(fixed_model, image_dataloader_test)
print(count)


# ### GPU! (This part is optional, 0 points)
# 
# If you have access to GPU, you can make the code run on GPU, it would be much faster. 
# 
# Now, we're going to switch the dtype of the model and our data to the GPU-friendly tensors, and see what happens... everything is the same, except we are casting our model and input tensors as this new dtype instead of the old one.
# 
# If this returns false, or otherwise fails in a not-graceful way (i.e., with some error message), you may not have an NVIDIA GPU available on your machine. 

# In[ ]:


# Verify that CUDA is properly configured and you have a GPU available

torch.cuda.is_available()


# In[41]:


import copy
gpu_dtype = torch.cuda.FloatTensor

fixed_model_gpu = copy.deepcopy(fixed_model_base)#.type(gpu_dtype)
fixed_model_gpu.cuda()
x_gpu = torch.randn(4, 3, 64, 64).cuda()#.type(gpu_dtype)
x_var_gpu = Variable(x_gpu)#type(gpu_dtype)) # Construct a PyTorch Variable out of your input data
ans = fixed_model_gpu(x_var_gpu)        # Feed it through the model! 

# Check to make sure what comes out of your model
# is the right dimensionality... this should be True
# if you've done everything correctly
np.array_equal(np.array(ans.size()), np.array([4, 10]))


# Run the following cell to evaluate the performance of the forward pass running on the CPU:

# In[23]:


get_ipython().run_cell_magic('timeit', '', 'ans = fixed_model(x_var)')


# ... and now the GPU:

# In[24]:


get_ipython().run_cell_magic('timeit', '', 'torch.cuda.synchronize() # Make sure there are no pending GPU computations\nans = fixed_model_gpu(x_var_gpu)        # Feed it through the model! \ntorch.cuda.synchronize() # Make sure there are no pending GPU computations')


# You should observe that even a simple forward pass like this is significantly faster on the GPU. So for the rest of the assignment (and when you go train your models in assignment 3 and your project!), you should use the GPU datatype for your model and your tensors: as a reminder that is *torch.cuda.FloatTensor* (in our notebook here as *gpu_dtype*)

# Let's make the loss function and training variables to GPU friendly format by '.cuda()'

# In[48]:


loss_fn = nn.CrossEntropyLoss().cuda()
optimizer = optim.Adam(fixed_model_gpu.parameters(), lr=1e-5)


# In[45]:


def train(model, loss_fn, optimizer, dataloader, num_epochs = 1):
    for epoch in range(num_epochs):
        print('Starting epoch %d / %d' % (epoch + 1, num_epochs))
        check_accuracy(fixed_model_gpu, image_dataloader_val)
        model.train()
        for t, sample in enumerate(dataloader):
            x_var = Variable(sample['image'].cuda())
            y_var = Variable(sample['Label'].cuda().long())

            scores = model(x_var)
            
            loss = loss_fn(scores, y_var)
            if (t + 1) % print_every == 0:
                print('t = %d, loss = %.4f' % (t + 1, loss.data[0]))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

def check_accuracy(model, loader):
    '''
    if loader.dataset.train:
        print('Checking accuracy on validation set')
    else:
        print('Checking accuracy on test set')  
    '''
    num_correct = 0
    num_samples = 0
    model.eval() # Put the model in test mode (the opposite of model.train(), essentially)
    for t, sample in enumerate(loader):
        x_var = Variable(sample['image'].cuda())
        y_var = sample['Label'].cuda()
        y_var=y_var.cpu()
        scores = model(x_var)
        _, preds = scores.data.cpu().max(1)
        #print(preds)
        #print(y_var)
        num_correct += (preds.numpy() == y_var.numpy()).sum()
        num_samples += preds.size(0)
    acc = float(num_correct) / num_samples
    print('Got %d / %d correct (%.2f)' % (num_correct, num_samples, 100 * acc))


# Run on GPU!

# In[49]:


torch.cuda.random.manual_seed(12345)

fixed_model_gpu.apply(reset) 
fixed_model_gpu.train() 
train(fixed_model_gpu, loss_fn, optimizer,image_dataloader_train, num_epochs=5) 
check_accuracy(fixed_model_gpu, image_dataloader_train)# check accuracy on the training set


# In[50]:


check_accuracy(fixed_model_gpu, image_dataloader_val)


# ### 3D Convolution on video clips (25 points+10 extra points)
# 3D convolution is for videos, it has one more dimension than 2d convolution. You can find the document for 3D convolution here http://pytorch.org/docs/master/nn.html#torch.nn.Conv3dIn. In our dataset, each clip is a video of 3 frames. Lets classify the each clip rather than each image using 3D convolution.
# We offer the data loader, the train_3d and check_accuracy

# In[53]:


class ActionClipDataset(Dataset):
    """Action Landmarks dataset."""

    def __init__(self,  root_dir,labels=[], transform=None):
        """
        Args:
            csv_file (string): Path to the csv file with annotations.
            root_dir (string): Directory with all the images.
            transform (callable, optional): Optional transform to be applied
                on a sample.
        """
        
        self.root_dir = root_dir
        self.transform = transform
        self.length=len(os.listdir(self.root_dir))
        self.labels=labels

    def __len__(self):
        return self.length

    def __getitem__(self, idx):
        
        folder=idx+1
        folder=format(folder,'05d')
        clip=[]
        if len(self.labels)!=0:
            Label=self.labels[idx][0]-1
        for i in range(3):
            imidx=i+1
            imgname=str(imidx)+'.jpg'
            img_path = os.path.join(self.root_dir,
                                    folder,imgname)
            image = Image.open(img_path)
            image=np.array(image)
            clip.append(image)
        if self.transform:
            clip=np.asarray(clip)
            clip=np.transpose(clip, (0,3,1,2))
            clip = torch.from_numpy(np.asarray(clip))
        if len(self.labels)!=0:
            sample={'clip':clip,'Label':Label,'folder':folder}
        else:
            sample={'clip':clip,'folder':folder}
        return sample

clip_dataset=ActionClipDataset(root_dir='../input/cse512f18hw6vid/data/data/trainClips/',                               labels=label_train,transform=T.ToTensor())#/home/tqvinh/Study/CSE512/cse512-s18/hw2data/trainClips/
for i in range(10):
    sample=clip_dataset[i]
    print(sample['clip'].shape)
    print(sample['Label'])
    print(sample['folder'])


# In[54]:


clip_dataloader = DataLoader(clip_dataset, batch_size=4,
                        shuffle=True, num_workers=4)


for i,sample in enumerate(clip_dataloader):
    print(i,sample['clip'].shape,sample['folder'],sample['Label'])
    if i>20: 
        break


# In[55]:


clip_dataset_train=ActionClipDataset(root_dir='../input/cse512f18hw6vid/data/data/trainClips',labels=label_train,transform=T.ToTensor())

clip_dataloader_train = DataLoader(clip_dataset_train, batch_size=16,
                        shuffle=True, num_workers=4)
clip_dataset_val=ActionClipDataset(root_dir='../input/cse512f18hw6vid/data/data/valClips',labels=label_val,transform=T.ToTensor())

clip_dataloader_val = DataLoader(clip_dataset_val, batch_size=16,
                        shuffle=True, num_workers=4)
clip_dataset_test=ActionClipDataset(root_dir='../input/cse512f18hw6vid/data/data/testClips',labels=[],transform=T.ToTensor())

clip_dataloader_test = DataLoader(clip_dataset_test, batch_size=16,
                        shuffle=False, num_workers=4)


# Write the Flatten for 3d covolution feature maps.

# In[56]:


class Flatten3d(nn.Module):
    def forward(self, x):
        ###############6th TODO (5 points)###################
        N, C, D, H, W = x.size() # store N, C, D, H, W
        return x.view(N, -1)  # flatten  values into a single vector 

        


# Design a network using 3D convolution on videos for video classification.

# In[57]:


fixed_model_3d = nn.Sequential( # You fill this in!
    ###############7th TODO (20 points)#########################
    nn.Conv3d(3,32, kernel_size=3, stride=1, padding=2),
    nn.BatchNorm3d(32),
    nn.ReLU(inplace=True),
    nn.MaxPool3d(kernel_size=2, stride=2),
    
    nn.Conv3d(32, 64, kernel_size=3, stride=1, padding=2),
    nn.BatchNorm3d(64),
    nn.ReLU(inplace=True),
    nn.MaxPool3d(kernel_size=2, stride=2),
    
    nn.Conv3d(64, 128, kernel_size=3, stride=1, padding=2),
    nn.BatchNorm3d(128),
    nn.ReLU(inplace=True),
    nn.MaxPool3d(kernel_size=2, stride=2),
    Flatten3d(),
    nn.ReLU(inplace=True),
    nn.Linear(20736, 10),   
    
)

fixed_model_3d = fixed_model_3d.type(dtype)
x = torch.randn(32,3, 3, 64, 64).type(dtype)
x_var = Variable(x).type(dtype) # Construct a PyTorch Variable out of your input data
ans = fixed_model_3d(x_var) 
np.array_equal(np.array(ans.size()), np.array([32, 10]))


# ### Describe what you did (5 points)
# 
# In the cell below you should write an explanation of what you did, any additional features that you implemented, and any visualizations or graphs that you make in the process of training and evaluating your network.

# ### 8th TODO Tell us here:
# 
# * 3\*3*3 Concolution layer with 32 filters 
# * Batch Normalization Layer
# * ReLU Layer
# * MaxPooling Layer of Size 2 with stride 2
# * 3\*3*3 Concolution layer with 64 filters 
# * Batch Normalization Layer
# * ReLU Layer
# * MaxPooling Layer of Size 2 with stride 2
# * 3\*3*3 Concolution layer with 128 filters 
# * Batch Normalization Layer
# * ReLU Layer
# * MaxPooling Layer of Size 2 with stride 2
# * Flatten 
# * ReLU Layer
# * Affine layer

# In[ ]:


loss_fn = nn.CrossEntropyLoss().type(dtype)
optimizer = optim.RMSprop(fixed_model_3d.parameters(), lr=1e-4)


# In[64]:


def train_3d(model, loss_fn, optimizer,dataloader,num_epochs = 1):
    for epoch in range(num_epochs):
        print('Starting epoch %d / %d' % (epoch + 1, num_epochs))
        model.train()
        for t, sample in enumerate(dataloader):
            x_var = Variable(sample['clip'].type(dtype))
            y_var = Variable(sample['Label'].type(dtype).long())

            scores = model(x_var)
            
            loss = loss_fn(scores, y_var)
            if (t + 1) % print_every == 0:
                print('t = %d, loss = %.4f' % (t + 1, loss.data[0]))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

def check_accuracy_3d(model, loader):
    '''
    if loader.dataset.train:
        print('Checking accuracy on validation set')
    else:
        print('Checking accuracy on test set')  
    '''
    num_correct = 0
    num_samples = 0
    model.eval() # Put the model in test mode (the opposite of model.train(), essentially)
    for t, sample in enumerate(loader):
        x_var = Variable(sample['clip'].type(dtype))
        y_var = sample['Label'].type(dtype)
        y_var=y_var.cpu()
        scores = model(x_var)
        _, preds = scores.data.cpu().max(1)
        #print(preds)
        #print(y_var)
        num_correct += (preds.numpy() == y_var.numpy()).sum()
        num_samples += preds.size(0)
    acc = float(num_correct) / num_samples
    print('Got %d / %d correct (%.2f)' % (num_correct, num_samples, 100 * acc))
    
    
    #GPU Code
    
# def train_3d(model, loss_fn, optimizer,dataloader,num_epochs = 1):
#     for epoch in range(num_epochs):
#         print('Starting epoch %d / %d' % (epoch + 1, num_epochs))
#         check_accuracy_3d(fixed_model_gpu, clip_dataloader_val)
#         model.train()
#         for t, sample in enumerate(dataloader):
#             x_var = Variable(sample['clip'].float().cuda())
#             y_var = Variable(sample['Label'].cuda().long())

#             scores = model(x_var)
            
#             loss = loss_fn(scores, y_var)
#             if (t + 1) % print_every == 0:
#                 print('t = %d, loss = %.4f' % (t + 1, loss.data[0]))
# #                 check_accuracy_3d(fixed_model_3d, clip_dataloader_val)
#             optimizer.zero_grad()
#             loss.backward()
#             optimizer.step()
        

# def check_accuracy_3d(model, loader):
#     '''
#     if loader.dataset.train:
#         print('Checking accuracy on validation set')
#     else:
#         print('Checking accuracy on test set')  
#     '''
#     num_correct = 0
#     num_samples = 0
#     model.eval() # Put the model in test mode (the opposite of model.train(), essentially)
#     for t, sample in enumerate(loader):
#         x_var = Variable(sample['clip'].float().cuda())
#         y_var = sample['Label'].cuda()
#         y_var=y_var.cpu()
#         scores = model(x_var)
#         _, preds = scores.data.cpu().max(1)
#         #print(preds)
#         #print(y_var)
#         num_correct += (preds.numpy() == y_var.numpy()).sum()
#         num_samples += preds.size(0)
#     acc = float(num_correct) / num_samples
#     print('Got %d / %d correct (%.2f)' % (num_correct, num_samples, 100 * acc))


# In[65]:


torch.cuda.random.manual_seed(12345)
fixed_model_3d.apply(reset) 
fixed_model_3d.train() 
train_3d(fixed_model_3d, loss_fn, optimizer,clip_dataloader_train, num_epochs=3) 
fixed_model_3d.eval() 
check_accuracy_3d(fixed_model_3d, clip_dataloader_val)


# GPU Code

# import copy
# gpu_dtype = torch.cuda.FloatTensor

# fixed_model_gpu = copy.deepcopy(fixed_model_3d)#.type(gpu_dtype)
# fixed_model_gpu.cuda()
# x_gpu = torch.randn(32,3, 3, 64, 64).cuda()#.type(gpu_dtype)
# x_var_gpu = Variable(x_gpu)#type(gpu_dtype)) # Construct a PyTorch Variable out of your input data
# ans = fixed_model_gpu(x_var_gpu)        # Feed it through the model! 
# np.array_equal(np.array(ans.size()), np.array([32, 10]))

# loss_fn = nn.CrossEntropyLoss().cuda()
# optimizer = optim.Adam(fixed_model_gpu.parameters(), lr=0.0001)


# torch.cuda.random.manual_seed(12345)

# fixed_model_gpu.apply(reset) 
# fixed_model_gpu.train() 
# train_3d(fixed_model_gpu, loss_fn, optimizer,clip_dataloader_train, num_epochs=5)


# In[70]:


check_accuracy_3d(fixed_model_gpu, clip_dataloader_val)


# Test your 3d convolution model on the validation set. You don't need to submit the result of this part to kaggle.  

# Test your model on the test set, predict_on_test_3d() will generate a file named 'results_3d.csv'. Please submit the csv file to kaggle https://www.kaggle.com/c/cse512springhw3video
# The highest 3 entries get extra 10 points.
# 

# In[69]:


def predict_on_test_3d(model, loader):
    '''
    if loader.dataset.train:
        print('Checking accuracy on validation set')
    else:
        print('Checking accuracy on test set')  
    '''
    num_correct = 0
    num_samples = 0
    model.eval() # Put the model in test mode (the opposite of model.train(), essentially)
    results=open('results_3d.csv','w')
    count=0
    results.write('Id'+','+'Class'+'\n')
    for t, sample in enumerate(loader):
        x_var = Variable(sample['clip'].type(dtype))
        scores = model(x_var)
        _, preds = scores.data.max(1)
        for i in range(len(preds)):
            results.write(str(count)+','+str(preds[i])+'\n')
            count+=1
    results.close()
    return count
    
count=predict_on_test_3d(fixed_model_3d, clip_dataloader_test)
print(count)

