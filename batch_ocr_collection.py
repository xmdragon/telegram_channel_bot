#!/usr/bin/env python3
"""
批量OCR样本收集脚本
对现有的媒体文件进行OCR识别并收集样本
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any
import time

# 添加项目路径
sys.path.append('.')

from app.services.ocr_service import ocr_service
from app.services.ocr_sample_manager import ocr_sample_manager
from app.core.training_config import TrainingDataConfig

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BatchOCRCollector:
    """批量OCR样本收集器"""
    
    def __init__(self):
        self.processed_count = 0
        self.success_count = 0
        self.error_count = 0
        self.sample_count = 0
        self.start_time = None
        
    async def collect_from_existing_media(self, limit: int = None) -> Dict[str, Any]:
        """从现有媒体文件收集OCR样本"""
        try:
            self.start_time = time.time()
            logger.info("🚀 开始批量OCR样本收集...")
            
            # 读取媒体元数据
            media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
            media_dir = Path("data/ad_training_data")
            
            if not media_metadata_file.exists():
                logger.error("媒体元数据文件不存在")
                return {"success": False, "error": "媒体元数据文件不存在"}
            
            data = json.load(open(media_metadata_file, 'r', encoding='utf-8'))
            media_files = data.get("media_files", {})
            
            # 筛选图片文件
            image_files = []
            for file_hash, info in media_files.items():
                if info.get("type") == "image":
                    file_path = media_dir / info["path"]
                    if file_path.exists():
                        image_files.append({
                            "hash": file_hash,
                            "path": str(file_path),
                            "info": info
                        })
            
            # 应用限制
            if limit:
                image_files = image_files[:limit]
            
            logger.info(f"📊 找到 {len(image_files)} 个图片文件待处理")
            
            # 批量处理
            await self._process_files(image_files)
            
            # 生成报告
            elapsed_time = time.time() - self.start_time
            
            report = {
                "success": True,
                "processed_count": self.processed_count,
                "success_count": self.success_count,
                "error_count": self.error_count,
                "sample_count": self.sample_count,
                "elapsed_time": f"{elapsed_time:.2f}秒",
                "average_time": f"{elapsed_time/max(self.processed_count, 1):.2f}秒/文件" if self.processed_count > 0 else "N/A"
            }
            
            logger.info("✅ 批量OCR收集完成!")
            logger.info(f"📈 处理统计: {self.processed_count}个文件, {self.success_count}个成功, {self.error_count}个失败")
            logger.info(f"📦 收集样本: {self.sample_count}个")
            logger.info(f"⏱️  总用时: {elapsed_time:.2f}秒")
            
            return report
            
        except Exception as e:
            logger.error(f"批量OCR收集失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _process_files(self, image_files: List[Dict]) -> None:
        """处理文件列表"""
        
        # 分批处理，避免内存过载
        batch_size = 5
        for i in range(0, len(image_files), batch_size):
            batch = image_files[i:i+batch_size]
            
            logger.info(f"🔄 处理批次 {i//batch_size + 1}/{(len(image_files)-1)//batch_size + 1} ({len(batch)}个文件)")
            
            # 并行处理当前批次
            tasks = []
            for file_item in batch:
                task = self._process_single_file(file_item)
                tasks.append(task)
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # 批次间短暂休息
            if i + batch_size < len(image_files):
                await asyncio.sleep(0.5)
    
    async def _process_single_file(self, file_item: Dict) -> None:
        """处理单个文件"""
        try:
            self.processed_count += 1
            file_hash = file_item["hash"]
            file_path = file_item["path"] 
            file_info = file_item["info"]
            
            logger.info(f"🔍 [{self.processed_count}] 处理: {Path(file_path).name}")
            
            # 执行OCR识别
            ocr_result = await ocr_service.extract_image_content(file_path)
            
            if not ocr_result:
                logger.warning(f"❌ OCR识别失败: {file_path}")
                self.error_count += 1
                return
            
            # 提取OCR信息
            texts = ocr_result.get('texts', [])
            qr_codes = []
            for qr in ocr_result.get('qr_codes', []):
                if isinstance(qr, dict):
                    qr_codes.append(qr.get('data', ''))
                else:
                    qr_codes.append(str(qr))
            
            ad_score = ocr_result.get('ad_score', 0)
            is_ad = file_info.get('is_ad', False)
            keywords_detected = ocr_result.get('ad_indicators', [])
            
            # 保存样本
            sample_saved = await ocr_sample_manager.save_sample(
                image_hash=file_hash,
                image_path=file_path,
                ocr_texts=texts,
                qr_codes=qr_codes,
                ad_score=ad_score,
                is_ad=is_ad,
                keywords_detected=keywords_detected,
                auto_rejected=False,  # 现有文件不是自动拒绝的
                rejection_reason="",
                message_id=file_info.get('message_ids', [None])[0],
                source_channel=file_info.get('channel_id')
            )
            
            if sample_saved:
                self.success_count += 1
                self.sample_count += 1
                
                # 记录识别结果
                text_info = f"识别{len(texts)}条文字" if texts else "无文字"
                qr_info = f", {len(qr_codes)}个二维码" if qr_codes else ""
                score_info = f", 广告分数{ad_score:.1f}"
                
                logger.info(f"✅ [{self.processed_count}] 成功: {text_info}{qr_info}{score_info}")
                
                # 如果有识别到内容，打印详细信息
                if texts or qr_codes:
                    if texts:
                        logger.info(f"   📝 文字: {', '.join(texts[:3])}{'...' if len(texts) > 3 else ''}")
                    if qr_codes:
                        logger.info(f"   🔗 二维码: {', '.join(qr_codes[:2])}{'...' if len(qr_codes) > 2 else ''}")
            else:
                logger.warning(f"❌ 样本保存失败: {file_path}")
                self.error_count += 1
                
        except Exception as e:
            logger.error(f"❌ 处理文件失败 {file_path}: {e}")
            self.error_count += 1

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='批量OCR样本收集')
    parser.add_argument('--limit', type=int, help='限制处理文件数量')
    parser.add_argument('--learn', action='store_true', help='处理完成后运行学习功能')
    
    args = parser.parse_args()
    
    # 创建收集器
    collector = BatchOCRCollector()
    
    # 开始收集
    result = await collector.collect_from_existing_media(limit=args.limit)
    
    if result["success"]:
        print("\n" + "="*60)
        print("📋 批量OCR收集报告")
        print("="*60)
        print(f"✅ 处理完成: {result['processed_count']} 个文件")
        print(f"📦 成功收集: {result['sample_count']} 个样本")
        print(f"❌ 处理失败: {result['error_count']} 个文件")
        print(f"⏱️  总用时: {result['elapsed_time']}")
        print(f"⚡ 平均速度: {result['average_time']}")
        
        # 获取最新统计信息
        stats = await ocr_sample_manager.get_statistics()
        print(f"\n📊 样本库统计:")
        print(f"   总样本数: {stats.get('total_samples', 0)}")
        print(f"   广告样本: {stats.get('ad_samples', 0)}")
        print(f"   非广告样本: {stats.get('non_ad_samples', 0)}")
        print(f"   高分样本(≥50): {stats.get('high_score_samples', 0)}")
        
        # 如果指定了学习参数，运行学习功能
        if args.learn and stats.get('ad_samples', 0) >= 10:
            print("\n🧠 开始学习过程...")
            learn_result = await ocr_sample_manager.learn_from_samples()
            if learn_result.get('success'):
                new_keywords = learn_result.get('new_keywords', [])
                if new_keywords:
                    print(f"✅ 学习完成，发现 {len(new_keywords)} 个新关键词:")
                    for keyword in new_keywords[:10]:  # 显示前10个
                        print(f"   - {keyword}")
                    if len(new_keywords) > 10:
                        print(f"   ... 还有 {len(new_keywords) - 10} 个")
                else:
                    print("✅ 学习完成，未发现新的关键词模式")
            else:
                print(f"❌ 学习失败: {learn_result.get('message', '未知错误')}")
        
        print("="*60)
    else:
        print(f"❌ 批量收集失败: {result.get('error', '未知错误')}")

if __name__ == "__main__":
    asyncio.run(main())