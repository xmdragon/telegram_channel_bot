"""
错误格式化工具 - 简化冗长的错误信息
"""
import re
import logging

logger = logging.getLogger(__name__)

def format_telethon_error(error_message: str) -> str:
    """
    格式化 Telethon 错误信息，简化冗长的字节数据

    Args:
        error_message: 原始错误信息

    Returns:
        简化后的错误信息
    """
    # 检查是否为 Constructor ID 错误
    if "Constructor ID" in error_message and "Remaining bytes:" in error_message:
        # 提取 Constructor ID
        constructor_match = re.search(r'Constructor ID ([a-fA-F0-9]+)', error_message)
        constructor_id = constructor_match.group(1) if constructor_match else "unknown"

        # 提取字节数据长度
        remaining_bytes_match = re.search(r"Remaining bytes: b'([^']*)", error_message)
        if remaining_bytes_match:
            bytes_data = remaining_bytes_match.group(1)
            # 计算字节长度（转义字符按实际字节计算）
            byte_count = len(bytes_data.encode().decode('unicode_escape').encode('latin1'))

            return f"Telethon协议解析错误: 未知Constructor ID {constructor_id} (剩余数据: {byte_count} 字节)"
        else:
            return f"Telethon协议解析错误: 未知Constructor ID {constructor_id}"

    # 检查是否包含大量字节数据
    if "Remaining bytes: b'" in error_message:
        # 截断字节数据，只显示前20个字符
        truncated = re.sub(
            r"Remaining bytes: b'[^']{20,}[^']*'",
            lambda m: f"Remaining bytes: {m.group(0)[:35]}...' (数据已截断)",
            error_message
        )
        return truncated

    # 一般的字节数据截断
    if len(error_message) > 500 and "\\x" in error_message:
        # 如果错误信息太长且包含字节数据，进行截断
        lines = error_message.split('\n')
        if len(lines) > 3:
            return f"{lines[0]}\n{lines[1]}\n... (错误信息已截断，共{len(lines)}行)"
        elif len(error_message) > 500:
            return f"{error_message[:500]}... (错误信息已截断)"

    return error_message


def log_telethon_error(logger_instance: logging.Logger, level: int, error: Exception, context: str = ""):
    """
    记录 Telethon 错误，自动格式化冗长信息

    Args:
        logger_instance: Logger 实例
        level: 日志级别
        error: 异常对象
        context: 上下文信息
    """
    error_str = str(error)
    formatted_error = format_telethon_error(error_str)

    # 如果错误被简化了，添加提示
    if len(formatted_error) < len(error_str):
        message = f"{context} {formatted_error}" if context else formatted_error
        logger_instance.log(level, message)
        logger_instance.debug(f"完整错误信息: {error_str}")
    else:
        message = f"{context} {formatted_error}" if context else formatted_error
        logger_instance.log(level, message)


class TelethonErrorHandler:
    """Telethon 错误处理器，用于包装和简化错误输出"""

    def __init__(self, logger_instance: logging.Logger):
        self.logger = logger_instance

    def handle_error(self, error: Exception, operation: str = "", level: int = logging.ERROR) -> str:
        """
        处理错误并返回简化的错误信息

        Args:
            error: 异常对象
            operation: 操作描述
            level: 日志级别

        Returns:
            简化的错误信息
        """
        context = f"[{operation}]" if operation else ""
        log_telethon_error(self.logger, level, error, context)
        return format_telethon_error(str(error))

    def is_protocol_error(self, error: Exception) -> bool:
        """检查是否为协议错误"""
        error_str = str(error)
        return "Constructor ID" in error_str or "Remaining bytes:" in error_str

    def is_connection_error(self, error: Exception) -> bool:
        """检查是否为连接错误"""
        error_str = str(error).lower()
        connection_indicators = [
            "connection", "timeout", "network", "proxy",
            "disconnect", "502", "503", "504"
        ]
        return any(indicator in error_str for indicator in connection_indicators)