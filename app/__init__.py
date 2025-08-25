# Telegram消息采集审核系统

# 抑制SentenceTransformers的无用警告
import warnings
import logging
warnings.filterwarnings('ignore', category=UserWarning, module='sentence_transformers')
warnings.filterwarnings('ignore', message='.*sentence-transformers model found.*')
logging.getLogger('sentence_transformers').setLevel(logging.ERROR)