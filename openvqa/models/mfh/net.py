# --------------------------------------------------------
# OpenVQA
# Licensed under The MIT License [see LICENSE for details]
# Written by Pengbing Gao https://github.com/nbgao
# --------------------------------------------------------

from openvqa.ops.fc import FC
from openvqa.models.mfh.mfh import *
from openvqa.models.mfh.adapter import Adapter

import torch.nn as nn
import torch.nn.functional as F
import torch


# ------------------------------
# ---- Flatten the sequence ----
# ------------------------------
'''
class AttFlat(nn.Module):
    def __init__(self, __C):
        super(AttFlat, self).__init__()
        self.__C = __C

        self.mlp = MLP(
            in_size=__C.HIDDEN_SIZE,
            mid_size=__C.FLAT_MLP_SIZE,
            out_size=__C.FLAT_GLIMPSES,
            dropout_r=__C.DROPOUT_R,
            use_relu=True
        )

        self.linear_merge = nn.Linear(
            __C.HIDDEN_SIZE * __C.FLAT_GLIMPSES,
            __C.FLAT_OUT_SIZE
        )

    def forward(self, x, x_mask):
        att = self.mlp(x)
        att = att.masked_fill(
            x_mask.squeeze(1).squeeze(1).unsqueeze(2),
            -1e9
        )
        att = F.softmax(att, dim=1)

        att_list = []
        for i in range(self.__C.FLAT_GLIMPSES):
            att_list.append(
                torch.sum(att[:, :, i: i + 1] * x, dim=1)
            )

        x_atted = torch.cat(att_list, dim=1)
        x_atted = self.linear_merge(x_atted)

        return x_atted
'''

# -------------------------
# ---- Main MFH Model ----
# -------------------------


class Net(nn.Module):
    def __init__(self, __C, pretrained_emb, token_size, answer_size):
        super(Net, self).__init__()
        self.__C = __C
        self.adapter = Adapter(__C)

        self.embedding = nn.Embedding(
            num_embeddings=token_size,
            embedding_dim=__C.WORD_EMBED_SIZE
        )

        self.lstm = nn.LSTM(
            input_size=__C.WORD_EMBED_SIZE,
            hidden_size=__C.HIDDEN_SIZE,
            num_layers=1,
            bidirectional=False
        )
        # Loading the GloVe embedding weights
        if __C.USE_GLOVE:
            self.embedding.weight.data.copy_(torch.from_numpy(pretrained_emb))

        self.question_attention = QuestionAttention(__C)
        self.image_attention = ImageAttention(__C)
        self.mfh1 = MFH(__C, __C.IMAGE_CHANNEL*__C.NUM_IMG_GLIMPSE, __C.HIDDEN_SIZE*__C.NUM_QUESTION_GLIMPSE, 0.1, True)
        self.mfh2 = MFH(__C, __C.IMAGE_CHANNEL*__C.NUM_IMG_GLIMPSE, __C.HIDDEN_SIZE*__C.NUM_QUESTION_GLIMPSE, 0.1, False)

        # Full Connection Layer
        self.linear = nn.Linear(2*__C.MFB_OUT_DIM, answer_size)

    def forward(self, frcn_feat, grid_feat, bbox_feat, ques_ix):
        # print('** frcn_feat:', frcn_feat.shape)         # N x 100 x 2048
        # print('** grid_feat:', grid_feat.shape)         # N x 1
        # print('** spat_feat:', bbox_feat.shape)         # N x 100 x 5
        # print('** ques_ix:', ques_ix.shape)             # N x T

        img_feat, img_feat_mask = self.adapter(frcn_feat, grid_feat, bbox_feat)  # N x 100 x 2048

        # Pre-process Language Feature
        que_feat = self.embedding(ques_ix)                # N x T x 300
        que_feat = torch.transpose(que_feat, 1, 0)        # T x N x 300
        # que_feat, _ = self.lstm(que_feat)		          # N x T x 1024
        # que_feat = torch.tanh(que_feat)                 # T x N x 300
        # que_feat, _ = self.lstm(que_feat)               # T x N x 1024
        # que_feat = self.dropout_lstm(que_feat)          # T x N x 1024
        # que_feat = que_feat.permute(1, 2, 0)            # N x 1024 x T

        # print('** que_feat:', que_feat.shape)
        # print('** img_feat:', img_feat.shape)

        que_feat = self.question_attention(que_feat)            # N x 2048
        fuse_feat = self.image_attention(img_feat, que_feat)    # N x 4096
        z1, exp1 = self.mfh1(fuse_feat.unsqueeze(1), que_feat.unsqueeze(1))        # N x 1000  N x 5000
        z2, exp2 = self.mfh2(fuse_feat.unsqueeze(1), que_feat.unsqueeze(1), exp1)  # N x 1000  N x 5000
        out_feat = torch.cat((z1.squeeze(1), z2.squeeze(1)), 1)                       # N x 2000
        out_feat = self.linear(out_feat)                            # N x 3129
        return out_feat

