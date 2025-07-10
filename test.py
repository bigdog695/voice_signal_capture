from funasr import AutoModel

model = AutoModel(
    model="/home/bigdog695/.cache/modelscope/hub/models/iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online")

# 推理音频文件（16k wav）
res = model.generate(input="../test.wav")
print(res)

