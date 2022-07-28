# -*- coding: utf-8 -*-
"""monet

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/17iggSvI8dujzDv4epAocmgIy-p-EcgPV
"""

import os

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image

import numpy as np
import pickle as pkl
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import ImageGrid

class Dataset(torch.utils.data.Dataset):

    def __init__(self, img_dir):
        img_dir = BASE_DATASET_PATH + "/" + img_dir + "/" # 이미지 디렉토리
        
        path_list = os.listdir(img_dir) # 지정한 디렉토리 내에 모든 파일과 디렉토리 이름의 리스트를(list형태로) 리턴 
        abspath = os.path.abspath(img_dir) # 경로명 img_dir 의 정규화된 절대버전을 반환
        
        self.img_dir = img_dir
        self.img_list = [os.path.join(abspath, path) for path in path_list] # 경로 합쳐주기

        self.transform = transforms.Compose([    # 여러 단계를 하나로 묶어서 변환
            transforms.Resize(IMG_SIZE), # 해상도 조절 # size : 만약에 sequence 형식으로 (h,w)로 입력을 한다면 h,w로 크기가 조정이되며, int형식으로 한 개의 수가 입력이 된다면 h, w중 작은 것이 입력된 수로 조정이 된다. 예를 들어, h>w라면 (size*h/w, size) 이렇게 크기가 재조정이 된다.
            transforms.ToTensor(), # 데이터를 tensor로 바꿈
            transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]), # normalize image between -1 and 1  # tensor로 가져와서 (평균 표준편차)로 정규화  # [평균r, 평균g, 평균b] [표준편차r, 표준편차g, 표준편차b] inplace=False 디폴트값
        ])


    def __len__(self):
        return len(self.img_list) # 이미지경로 리스트 길이 리턴


    def __getitem__(self, idx): # 슬라이싱을 할 수 있도록 도우면서 객체에서도 슬라이싱 할려면 얘가 있어야한다. index를 인수로 받아야한다.
        path = self.img_list[idx] # 슬라이싱 사용할 속성
        img = Image.open(path).convert('RGB') # 이미지 열어서 RGB로 변환

        img_tensor = self.transform(img)
        return img_tensor

class Discriminator(nn.Module):

    def __init__(self,conv_dim=32):
        super(Discriminator, self).__init__()

        self.main = nn.Sequential(
            nn.Conv2d(3, conv_dim, 4, stride=2, padding=1),           # ***(채널 수, conv_dim : filter값 32가 디폴트값, kernel size, stride, padding)
            nn.LeakyReLU(0.2, inplace=True),                                  # ***LeakyReLU를 사용, 음수의 기울기(알파)=0.2 # SELU로 바꿔서 돌렷엇음
                                                                    # inplace 하면 input으로 들어온 것 자체를 수정하겠다는 뜻. 메모리 usage가 좀 좋아짐. 하지만 input을 없앰.
            nn.Conv2d(conv_dim, conv_dim*2, 4, stride=2, padding=1),
            nn.InstanceNorm2d(conv_dim*2),                             # 배치 의 각 요소를 독립적으로 즉 공간위치에서만 정규화합니다.  이미지라서 2d를 사용한거 같습니다.
            nn.LeakyReLU(0.2, inplace=True),

            nn.Conv2d(conv_dim*2, conv_dim*4, 4, stride=2, padding=1),
            nn.InstanceNorm2d(conv_dim*4),
            nn.LeakyReLU(0.2, inplace=True),

            nn.Conv2d(conv_dim*4, conv_dim*8, 4, padding=1),
            nn.InstanceNorm2d(conv_dim*8),
            nn.LeakyReLU(0.2, inplace=True),

            nn.Conv2d(conv_dim*8, 1, 4, padding=1),
        )

    def forward(self, x): # layer와 출력 output을 반환 (self와 x를 넣어주고 input이 하나일 때 x만 넣어도됨)
        x = self.main(x)
        x = F.avg_pool2d(x, x.size()[2:]) # kernel size에서 표현되는 픽셀들의 평균을 뽑아냄 / overfitting 방지
        x = torch.flatten(x, 1)
        return x

class ResidualBlock(nn.Module): # U-Net 대신 ResNet 사용 (184p)
    def __init__(self, in_channels):
        super(ResidualBlock, self).__init__() # 자식클래스에서 부모클래스의 내용을 사용하고 싶을 때 # block단위로 파라미터를 전달하기전에 이전의 값을 더하는 방식  ( 그래서 스킵이라고 말함 )

        self.main = nn.Sequential(
            nn.ReflectionPad2d(1),           # 입력경계에 반사를 사용하여 입력 tensor를 채움        
            nn.Conv2d(in_channels, in_channels, 3), # in_channels : 입력이미지 convolution에 의해 생성된 채널의 수 
            nn.InstanceNorm2d(in_channels),
            nn.ReLU(inplace=True),
            nn.ReflectionPad2d(1),
            nn.Conv2d(in_channels, in_channels, 3),
            nn.InstanceNorm2d(in_channels)
        )

    def forward(self, x):
        return x + self.main(x)

class Generator(nn.Module):
    def __init__(self, conv_dim=64, n_res_block=9): # ***
        super(Generator, self).__init__() 
        self.main = nn.Sequential(
            nn.ReflectionPad2d(3),  # input이랑 똑같이 패딩영역에 반전하여 복사하여 채움 
            nn.Conv2d(3, conv_dim, 7), ## ***
            nn.InstanceNorm2d(64),
            nn.ReLU(inplace=True), ## ***

            nn.Conv2d(conv_dim, conv_dim*2, 3, stride=2, padding=1),
            nn.InstanceNorm2d(conv_dim*2),
            nn.ReLU(inplace=True),
            nn.Conv2d(conv_dim*2, conv_dim*4, 3, stride=2, padding=1),
            nn.InstanceNorm2d(conv_dim*4),
            nn.ReLU(inplace=True),

            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),
            ResidualBlock(conv_dim*4),

            nn.ConvTranspose2d(conv_dim*4, conv_dim*2, 3, stride=2, padding=1, output_padding=1),
            nn.InstanceNorm2d(conv_dim*2),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(conv_dim*2, conv_dim, 3, stride=2, padding=1, output_padding=1),
            nn.InstanceNorm2d(conv_dim),
            nn.ReLU(inplace=True),

            nn.ReflectionPad2d(3),
            nn.Conv2d(conv_dim, 3, 7),
            nn.Tanh() # -1 부터 1까지 그래프 # 미분가능하고 음수일 때 음수로 강하고 나오고 0인경우 0 매핑 # 두 클래스간의 분류에서 사용 많이함
        )

    def forward(self, x):
        return self.main(x)

"""### class CycleGAN의 설명 (178p)
: 생성자는 쌍을 이루는 이미지가 데이터셋에 없기 때문에 바로 컴파일할 수 없다. 대신 세가지 조건으로 생성자를 동시에 평가한다.(y 모네그림 x 사진)


1) 유효성 : 각 생성자가 만든 이미지가 대응되는 판별자를 속이는가

- D_X 에 fake_x(G_YtoX가 생성한 가짜 이미지)를 넣어서 차이점 학습
- D_Y 에 fake_Y(G_XtoY 가 생성한 가짜 이미지)를 넣어서 차이점 학습

2) 재구성 : 두 생성자를 교대로 적용하면 원본이미지를 얻을 수 있는가

- G_YtoX에 fake_Y(G_XtoY 가 생성한 가짜 이미지 = 원본은 X )를 넣었을 때 원본 X를 다시 얻을 수 있는가 
- G_XtoY에 fake_X(G_YtoX 가 생성한 가짜 이미지 = 원본은 Y )를 넣었을 때 원본 Y를 다시 얻을 수 있는가 

3) 동일성 : 각 생성자를 자신의 타깃 도메인에 있는 이미지를 적용했을 때 이미지가 바뀌지 않고 그대로 남아 있는가

- G_YtoX 에 원본 X를 넣으면 원본 X가 그대로 나오는가
- G_XtoY 에 원본 Y를 넣으면 원본 Y가 그대로 나오는가

⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇

"""

class CycleGAN:

    def __init__(self, g_conv_dim=64, d_conv_dim=64, n_res_block=6): # ***
        self.device = torch.device('cuda') if torch.cuda.is_available() else torch.device("cpu") #*** cuda 디바이스 이용

        self.G_XtoY = Generator(conv_dim=g_conv_dim, n_res_block=n_res_block).to(self.device) # 생성자 생성
        self.G_YtoX = Generator(conv_dim=g_conv_dim, n_res_block=n_res_block).to(self.device)

        self.D_X = Discriminator(conv_dim=d_conv_dim).to(self.device) # 판별자 생성
        self.D_Y = Discriminator(conv_dim=d_conv_dim).to(self.device)

        print(f"Models running of {self.device}")

    def load_model(self, filename):
        save_filename = os.path.splitext(os.path.basename(filename))[0] + '.pt' # 파일이름 0번째 인덱스 스플릿 후 .pt 붙여서 저장
        return torch.load(save_filename)

    def real_mse_loss(self, D_out):     # 진짜 이미지 mse오차
        return torch.mean((D_out-1)**2) # 진짜 이미지는 1이니까 D_out에서 1을 빼고 제곱


    def fake_mse_loss(self, D_out):   # 가짜 이미지 mse오차
        return torch.mean(D_out**2) # 가짜 이미지는 0이니까 D_out에서 0을 빼고 제곱

    def cycle_consistency_loss(self, real_img, reconstructed_img, lambda_weight):
        reconstr_loss = torch.mean(torch.abs(real_img - reconstructed_img)) # 진짜이미지에서 다시 만든 이미지 뺀 절대값 평균 ( 새로만든 이미지 손실 보기 위해)
        return lambda_weight*reconstr_loss    

    
    def train_generator(self, optimizers, images_x, images_y): # 생성자 훈련
        # Generator YtoX
        optimizers["g_optim"].zero_grad()

        fake_images_x = self.G_YtoX(images_y)

        d_real_x = self.D_X(fake_images_x)
        g_YtoX_loss = self.real_mse_loss(d_real_x)

        recon_y = self.G_XtoY(fake_images_x)
        recon_y_loss = self.cycle_consistency_loss(images_y, recon_y, lambda_weight=10) # ***


        # Generator XtoY
        fake_images_y = self.G_XtoY(images_x)

        d_real_y = self.D_Y(fake_images_y)
        g_XtoY_loss = self.real_mse_loss(d_real_y)

        recon_x = self.G_YtoX(fake_images_y)
        recon_x_loss = self.cycle_consistency_loss(images_x, recon_x, lambda_weight=10)

        g_total_loss = g_YtoX_loss + g_XtoY_loss + recon_y_loss + recon_x_loss
        g_total_loss.backward()
        optimizers["g_optim"].step()

        return g_total_loss.item()

    
    def train_discriminator(self, optimizers, images_x, images_y): # 판별자 훈련
        # Discriminator x
        optimizers["d_x_optim"].zero_grad()

        d_real_x = self.D_X(images_x)
        d_real_loss_x = self.real_mse_loss(d_real_x)
        
        fake_images_x = self.G_YtoX(images_y)

        d_fake_x = self.D_X(fake_images_x)
        d_fake_loss_x = self.fake_mse_loss(d_fake_x)
        
        d_x_loss = d_real_loss_x + d_fake_loss_x
        d_x_loss.backward()
        optimizers["d_x_optim"].step()


        # Discriminator y
        optimizers["d_y_optim"].zero_grad()
            
        d_real_y = self.D_Y(images_y)
        d_real_loss_x = self.real_mse_loss(d_real_y)
    
        fake_images_y = self.G_XtoY(images_x)

        d_fake_y = self.D_Y(fake_images_y)
        d_fake_loss_y = self.fake_mse_loss(d_fake_y)

        d_y_loss = d_real_loss_x + d_fake_loss_y
        d_y_loss.backward()
        optimizers["d_y_optim"].step()

        return d_x_loss.item(), d_y_loss.item()


    def train(self, optimizers, data_loader_x, data_loader_y, print_every=1, sample_every=100):
        losses = []
        g_total_loss_min = np.Inf
    
        fixed_x = next(iter(data_loader_x))[1].to(self.device)
        fixed_y = next(iter(data_loader_y))[1].to(self.device)

        print(f'Running on {self.device}')
        for epoch in range(EPOCHS):
            for (images_x, images_y) in zip(data_loader_x, data_loader_y):
                images_x, images_y = images_x.to(self.device), images_y.to(self.device)
                
                g_total_loss = self.train_generator(optimizers, images_x, images_y) # 생성자 손실 총합 이걸 줄이는게 목표
                d_x_loss, d_y_loss = self.train_discriminator(optimizers, images_x, images_y) # 판별자x 손실 판별자 y 손실
                
            
            if epoch % print_every == 0:
                losses.append((d_x_loss, d_y_loss, g_total_loss))
                print('Epoch [{:5d}/{:5d}] | d_X_loss: {:6.4f} | d_Y_loss: {:6.4f} | g_total_loss: {:6.4f}'
                .format(
                    epoch, 
                    EPOCHS, 
                    d_x_loss, 
                    d_y_loss, 
                    g_total_loss
                ))
                
            if g_total_loss < g_total_loss_min:
                g_total_loss_min = g_total_loss
                
                torch.save(self.G_XtoY.state_dict(), "G_X2Y")
                torch.save(self.G_YtoX.state_dict(), "G_Y2X")
                
                torch.save(self.D_X.state_dict(), "D_X")
                torch.save(self.D_Y.state_dict(), "D_Y")
                
                print("Models Saved")
                
                

        return losses

from google.colab import drive
drive.mount('/content/drive')
#%cd /content/drive/MyDrive/MultiCampus/프젝

BASE_DATASET_PATH = "./gan-getting-started"
X_DATASET = "photo_jpg"
Y_DATASET = "monet_jpg"

BATCH_SIZE = 32 # ***
N_WORKERS = 0 # *** 0이 Default값이며, 0은 Main Process에 데이터를 불러오는 것 , 만약 Multi-Processing을 이용해서 데이터를 로드할 경우 Process의 개수에 맞게 할당하여 인자값을 조절함

IMG_SIZE = 128 # ***
LR = 0.0002 # *** lr=0.001이 디폴트
# alpha =0.001이 디폴트값 
BETA1 = 0.5 # *** 0.9가 디폴트값 
BETA2 = 0.999 # ***

EPOCHS =  # ***

# Dataset
x_dataset = Dataset(X_DATASET) # 데이터셋 경로
y_dataset = Dataset(Y_DATASET)


data_loader_x = DataLoader(x_dataset, BATCH_SIZE, shuffle=True, num_workers=N_WORKERS) # 데이터불러오기(경로, 배치 사이즈, 셔플하겟다, num_workers는 현재 작업하고 있는 환경 내에서 어떤 프로세스에 데이터를 불러올 것인지 조정하는 것)
data_loader_y = DataLoader(y_dataset, BATCH_SIZE, shuffle=True, num_workers=N_WORKERS)

# Model
cycleGan = CycleGAN()

# Optimizer
g_params = list(cycleGan.G_XtoY.parameters()) + list(cycleGan.G_YtoX.parameters()) 

optimizers = { # ***
    "g_optim": optim.Adam(g_params, LR, [BETA1, BETA2]), # X -> Y , Y -> X 이미지 변환을 학습 
    "d_x_optim": optim.Adam(cycleGan.D_X.parameters(), LR, [BETA1, BETA2]), # X 진짜 이미지와 G_YtoX가 생성한 가짜 이미지의 차이점을 학습 & 식별
    "d_y_optim": optim.Adam(cycleGan.D_Y.parameters(), LR, [BETA1, BETA2]) # Y 진짜 이미지와 G_XtoY가 생성한 가짜 이미지의 차이점을 학습 & 식별
}

# Train
losses = cycleGan.train(optimizers, data_loader_x, data_loader_y) # cycleGan class 안에 (불러오는 순서) : cycle_consistency_loss(판별자 생성 오류 ) -> train_generator -> train_generator & train_discriminator -> train

samples = []

for i in range(12): 
    fixed_x = next(iter(data_loader_x))[i].to(cycleGan.device) # x의 데이터를 하나씩 뽑아가며 torch.device 'cuda'(gpu 기술) 를 사용하거나, 안될경우 'cpu'사용하는 cycleGan.device로 보냄
    fake_y = cycleGan.G_XtoY(torch.unsqueeze(fixed_x, dim=0)) # fixed_x의 차원을 늘려서 Generator(=cycleGan.G_XyoY)에 넣음 
    samples.extend([fixed_x, torch.squeeze(fake_y, 0)]) # fa

fig = plt.figure(figsize=(18, 14)) # 도화지 size 설정
grid = ImageGrid(fig, 111, nrows_ncols=(2, 4), axes_pad=0.5) # 한번에 여러개의 그래프를 보여준다 / nrows_ncols는 그림이 나타날 행과 열을 설정


for i, (ax, im) in enumerate(zip(grid, samples)): # grid와 samples를 동시에 포문을 돌림 + tuple로 변환 후 각각의 번호를 할당
    _, w, h = im.size() #전체 원소의 개수
    im = im.detach().cpu().numpy() # 최적화된 모델을  연산 기록으로 부터 분리한 tensor을 반환 GPU 메모리에 올려져 있는 tensor를 cpu 메모리로 복사 이것을 numpy로
    im = np.transpose(im, (1, 2, 0)) # (batch_size, input_dim, hidden_dim) input_dim 이랑 hidden_dim 을 맞교환 ## contiguous와 transpose 보통 같이 사용함 
    
    im = ((im +1)*255 / (2)).astype(np.uint8) 
    ax.imshow(im.reshape((w,h,3))) #reshape하고 보여줌

    ax.xaxis.set_visible(False) 
    ax.yaxis.set_visible(False)

    if i%2 == 0: title = "Original"
    else: title = "fake"

    ax.set_title(title)

plt.show()

cycleGan.G_XtoY.summary()

def reverse_normalize(image, mean_=mean_, std_=std_):
    if torch.is_tensor(image):
        image = image.detach().numpy()
    un_normalized_img = image * std_ + mean_
    un_normalized_img = un_normalized_img * 255
    return np.uint8(un_normalized_img)

cycleGan.G_XtoY.eval() # evaluation 과정에서 사용하지 않아야 하는 layer들을 알아서 off 시키도록 하는 함수

#Get data loader for final transformation / submission
photo_dataset = Dataset('../gan-getting-started/photo_jpg/')
submit_dataloader = DataLoader(photo_dataset, batch_size=1, shuffle=False, pin_memory=True)
dataiter = iter(submit_dataloader) # iter() 반복하면서 뽑아주는 것

#Previous normalization choosen
mean_ = 0.5 
std_ = 0.5

#Loop through each picture
for image_idx in range(0, len(submit_dataloader)):
    with torch.no_grad(): # 메모리 사용량을 줄이고 계산 속도를 빠르게 해줌   
    #Get base picture
        fixed_X = dataiter.next() # iter로 iterator를 만들고 next로 반복을 수행
    
    #Identify correct device
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu") # torch.device 'cuda'(gpu 기술) 를 사용하거나 안될경우 'cpu'사용
    
    #Create fake pictures (monet-esque)
    fake_Y = cycleGan.G_XtoY(fixed_X.to(device)) # 최적화된 모델로 만들어준다
    fake_Y = fake_Y.detach().cpu().numpy() #  # 최적화된 모델을  연산 기록으로 부터 분리한 tensor을 반환 GPU 메모리에 올려져 있는 tensor를 cpu 메모리로 복사 이것을 numpy로
    fake_Y = reverse_normalize(fake_Y, mean_, std_) # 정규화된 것을 다시 풀어주는 것
    fake_Y = fake_Y[0].transpose(1, 2, 0) # (batch_size, input_dim, hidden_dim) input_dim 이랑 hidden_dim 을 맞교환 ## contiguous와 transpose 보통 같이 사용함 
    fake_Y = np.uint8(fake_Y) # 이미지 모양 제대로 나오게 저장
    fake_Y = Image.fromarray(fake_Y) # NumPy 배열로 되어있는 이미지 배열을 PIL 이미지로 변환
    #print(fake_Y.shape)
    
    #Save picture
    fake_Y.save("./images/" + str(image_idx) + ".jpg") # 이미지 저장

#Back to it
cycleGan.G_XtoY.train() # eval()을 사용하면 train()을 꼭 넣어야 한다