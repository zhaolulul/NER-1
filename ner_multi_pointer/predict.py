#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""do inference"""
import argparse
import logging
import os
import random

import torch

import utils
from metrics_utils import pointer2bio
from dataloader import MRCNERDataLoader
from model import BertMultiPointer
from transformers import RobertaConfig

# 参数解析器
parser = argparse.ArgumentParser()
# 设定参数
parser.add_argument('--seed', type=int, default=2333, help="random seed for initialization")
parser.add_argument('--restore_file', default=None, required=False,
                    help="Optional, name of the file containing weights to reload before training")
parser.add_argument('--mode', default='test', help="'val' or 'test'")


def predict(model, test_dataloader, params, mode):
    """预测并将结果输出至文件
    :param mode: 'val' or 'test'
    """
    model.eval()
    # init
    pre_result = []
    mask_lst = []

    # idx to label
    cate_idx2label = {idx: int(idx + 1) for idx, _ in enumerate(params.label_list)}

    # get data
    for batch in test_dataloader:
        # to device
        batch = tuple(t.to(params.device) for t in batch)
        input_ids, input_mask, start_pos, end_pos = batch
        # inference
        with torch.no_grad():
            start_logits, end_logits = model(input_ids, attention_mask=input_mask)

        # predict label
        start_label = start_logits.detach().cpu().numpy().transpose((0, 2, 1)).tolist()
        end_label = end_logits.detach().cpu().numpy().transpose((0, 2, 1)).tolist()
        # mask
        input_mask = input_mask.to("cpu").detach().numpy().tolist()

        # get result
        for start_p_s, end_p_s, input_mask_s in zip(start_label, end_label, input_mask):
            # 有效长度
            act_len = sum(input_mask_s)
            for idx, (start_p, end_p) in enumerate(zip(start_p_s, end_p_s)):
                pre_bio_labels = pointer2bio(start_p[:act_len], end_p[:act_len],
                                             ne_cate=cate_idx2label[idx])
                pre_result.append(pre_bio_labels)

    # write to file
    with open(params.data_dir / f'{mode}_tags_pre.txt', 'w', encoding='utf-8') as file_tags:
        for idx, tag in enumerate(pre_result):
            # 真实标签
            file_tags.write('{}\n'.format(' '.join(tag)))


if __name__ == '__main__':
    args = parser.parse_args()
    params = utils.Params()
    # 预测验证集还是测试集
    mode = args.mode
    # 设置模型使用的gpu
    torch.cuda.set_device(7)
    # 查看现在使用的设备
    print('current device:', torch.cuda.current_device())

    # Set the random seed for reproducible experiments
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    params.seed = args.seed

    # Set the logger
    utils.set_logger(save=False)

    # Load training data and val data
    dataloader = MRCNERDataLoader(params)

    # Define the model
    logging.info('Loading the model...')
    config_path = os.path.join(params.bert_model_dir, 'config.json')
    config = RobertaConfig.from_json_file(config_path)
    model = BertMultiPointer(config, params=params)
    model.to(params.device)

    # Reload weights from the saved file
    utils.load_checkpoint(os.path.join(params.model_dir, args.restore_file + '.pth.tar'), model)
    logging.info('- done.')

    # Create the input data pipeline
    logging.info("Loading the dataset...")
    loader = dataloader.get_dataloader(data_sign=mode)
    logging.info('-done')

    logging.info("Starting prediction...")
    predict(model, loader, params, mode)
    logging.info('-done')
