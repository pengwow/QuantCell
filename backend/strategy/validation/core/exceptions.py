"""
验证模块异常定义
"""


class ValidationError(Exception):
    """
    验证错误基类
    """

    def __init__(self, message: str, validator_name: str = None, details: dict = None):
        super().__init__(message)
        self.validator_name = validator_name
        self.details = details or {}


class ThresholdExceededError(ValidationError):
    """
    阈值超出错误
    当验证结果超出预设阈值时抛出
    """

    def __init__(
        self,
        message: str,
        validator_name: str = None,
        expected_value=None,
        actual_value=None,
        difference: float = None,
        threshold: float = None,
        details: dict = None,
    ):
        super().__init__(message, validator_name, details)
        self.expected_value = expected_value
        self.actual_value = actual_value
        self.difference = difference
        self.threshold = threshold

    def __str__(self):
        base_msg = super().__str__()
        return (
            f"{base_msg} | "
            f"期望值: {self.expected_value}, "
            f"实际值: {self.actual_value}, "
            f"差异: {self.difference:.6f}, "
            f"阈值: {self.threshold}"
        )


class ValidationSuiteError(ValidationError):
    """
    验证套件错误
    """

    pass


class ValidatorNotFoundError(ValidationError):
    """
    验证器未找到错误
    """

    pass


class DataFormatError(ValidationError):
    """
    数据格式错误
    """

    pass
