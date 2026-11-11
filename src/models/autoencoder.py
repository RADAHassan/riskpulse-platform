import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import joblib
from pathlib import Path
from src.config import ARTIFACTS_DIR, RANDOM_STATE

torch.manual_seed(RANDOM_STATE)
np.random.seed(RANDOM_STATE)

class TabularAutoencoder(nn.Module):
    def __init__(self, input_dim, bottleneck_dim=8):
        super().__init__()
        # Encoder: compress input down to bottleneck representation
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 20),
            nn.BatchNorm1d(20),
            nn.LeakyReLU(0.1),
            nn.Linear(20, bottleneck_dim),
            nn.BatchNorm1d(bottleneck_dim),
            nn.LeakyReLU(0.1)
        )
        # Decoder: reconstruct original features from bottleneck
        self.decoder = nn.Sequential(
            nn.Linear(bottleneck_dim, 20),
            nn.BatchNorm1d(20),
            nn.LeakyReLU(0.1),
            nn.Linear(20, input_dim)
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstruction = self.decoder(latent)
        return reconstruction, latent

class AutoencoderFeatureExtractor:
    def __init__(self, bottleneck_dim=8, epochs=12, batch_size=512, lr=1e-3):
        self.bottleneck_dim = bottleneck_dim
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.model = None

    def fit(self, X_train_legit):
        input_dim = X_train_legit.shape[1]
        self.model = TabularAutoencoder(input_dim=input_dim, bottleneck_dim=self.bottleneck_dim)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr, weight_decay=1e-5)
        criterion = nn.MSELoss()

        tensor_x = torch.tensor(X_train_legit, dtype=torch.float32)
        dataset = TensorDataset(tensor_x)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        self.model.train()
        for epoch in range(self.epochs):
            for batch in loader:
                x_b = batch[0]
                recon, _ = self.model(x_b)
                loss = criterion(recon, x_b)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        return self

    def transform(self, X):
        self.model.eval()
        with torch.no_grad():
            tensor_x = torch.tensor(X, dtype=torch.float32)
            recon, latent = self.model(tensor_x)
            # Compute element-wise squared error across features
            recon_error = torch.mean((tensor_x - recon) ** 2, dim=1, keepdim=True)
            
            error_np = recon_error.cpu().numpy()
            latent_np = latent.cpu().numpy()
            
        # Return reconstruction error + bottleneck representations
        return np.hstack([error_np, latent_np])

    def save(self, path):
        joblib.dump(self, path)

    @staticmethod
    def load(path):
        return joblib.load(path)
