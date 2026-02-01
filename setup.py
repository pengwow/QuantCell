from setuptools import setup, find_packages

setup(
    name="quantcell",          # 项目名
    version="0.1",        # 版本
    packages=find_packages(),  # 自动识别backend
    python_requires=">=3.12",   # Python版本要求
)