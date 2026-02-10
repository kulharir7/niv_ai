from setuptools import setup, find_packages
import re

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# Check Frappe version at install time
try:
    import frappe
    version_match = re.match(r"(\d+)", frappe.__version__)
    if version_match:
        major = int(version_match.group(1))
        if major < 14:
            raise SystemExit(
                f"Niv AI requires Frappe >= 14.0.0, found {frappe.__version__}. "
                "Please upgrade Frappe before installing."
            )
except ImportError:
    # Frappe not yet installed — bench will handle dependency order
    pass

setup(
    name="niv_ai",
    version="0.3.0",
    description="Niv AI - Complete AI Chat Assistant for ERPNext",
    author="Ravindra Kulhari",
    author_email="kulharir7@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.8",
)
