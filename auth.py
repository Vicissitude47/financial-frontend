import streamlit as st
import json
import os
import sys
from typing import Optional, Dict, Tuple
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 配置
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

# 从Streamlit secrets获取配置
ALLOWED_EMAILS = set(st.secrets["google_oauth"]["allowed_emails"])

def is_cloud_env() -> bool:
    """检查是否在云环境中运行"""
    # 如果不是本地环境，就认为是云环境
    return not is_local_env()

def is_local_env() -> bool:
    """检查是否在本地开发环境中运行"""
    try:
        # 检查是否在 Streamlit Cloud 上运行
        if os.environ.get("STREAMLIT_DEPLOYMENT_URL"):
            st.write("Debug - Cloud environment detected via STREAMLIT_DEPLOYMENT_URL")
            return False
            
        # 检查当前URL
        try:
            import streamlit.web.server.server as server
            current_url = server.get_url()
            st.write("Debug - Current URL:", current_url)
            if "streamlit.app" in current_url:
                st.write("Debug - Cloud environment detected via URL")
                return False
        except:
            st.write("Debug - Could not get current URL")
            
        # 检查主机名
        import socket
        hostname = socket.gethostname()
        st.write("Debug - Hostname:", hostname)
        
        # 检查是否在 Streamlit Cloud 上运行的其他标志
        is_cloud = any([
            bool(os.environ.get("STREAMLIT_PUBLIC_PORT")),  # Streamlit Cloud 设置
            bool(os.environ.get("STREAMLIT_SERVER_PORT")),  # Streamlit Cloud 设置
            bool(os.environ.get("STREAMLIT_SERVER_ADDRESS")),  # Streamlit Cloud 设置
            "streamlit.app" in hostname.lower(),      # Streamlit Cloud 主机名
        ])
        
        if is_cloud:
            st.write("Debug - Cloud environment detected via environment check")
            return False
            
        # 本地环境的判断条件
        is_local = (
            hostname.startswith("DESKTOP-") or  # Windows 桌面主机名
            hostname.startswith("MacBook") or   # Mac 主机名
            hostname == "localhost"
        )
        
        st.write("Debug - Final local environment check result:", is_local)
        return is_local
        
    except Exception as e:
        st.write("Debug - Error in environment detection:", str(e))
        # 如果检测失败，默认为云环境（更安全的选择）
        return False

def try_port(flow, start_port: int = 8502, max_attempts: int = 3) -> Optional[Credentials]:
    """尝试在不同端口运行OAuth服务器"""
    for port in range(start_port, start_port + max_attempts):
        try:
            return flow.run_local_server(port=port)
        except OSError:
            if port == start_port + max_attempts - 1:  # 最后一次尝试
                raise
            continue
    return None

def get_auth_url(client_config: Dict) -> Tuple[str, InstalledAppFlow]:
    """生成授权URL并返回flow对象"""
    flow = InstalledAppFlow.from_client_config(
        client_config,
        SCOPES,
        redirect_uri=st.secrets["google_oauth"]["redirect_uri"]
    )
    
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # 强制显示同意页面以确保获取refresh token
    )
    
    return auth_url, flow

class GoogleAuthManager:
    def __init__(self):
        self.creds = None
        self._load_credentials()
    
    def _load_credentials(self):
        """加载或刷新Google认证凭据"""
        # 首先尝试从session state加载凭据
        if 'oauth_credentials' in st.session_state:
            self.creds = st.session_state.oauth_credentials
            if self.creds and self.creds.valid:
                return

        # 如果没有有效凭据，创建新的OAuth flow
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    st.error(f"刷新令牌失败: {str(e)}")
                    self.creds = None
            
            if not self.creds:
                # 从secrets创建client config
                client_config = {
                    "web": {
                        "client_id": st.secrets["google_oauth"]["client_id"],
                        "client_secret": st.secrets["google_oauth"]["client_secret"],
                        "redirect_uris": [st.secrets["google_oauth"]["redirect_uri"]],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                }
                
                auth_url, flow = get_auth_url(client_config)
                
                # 显示授权说明
                st.markdown("""
                ### Google 登录说明
                
                1. **右键点击**下方链接，选择"在新标签页中打开"
                2. 使用允许的Google账号登录并授权
                3. 在新标签页中，当看到"此站点无法访问"时，从地址栏复制完整的URL
                4. 将URL粘贴到下方输入框
                
                **提示：** 
                - 一定要右键在新标签页中打开，否则URL会消失
                - 看到"此站点无法访问"是正常的，此时URL中已包含授权码
                """)
                
                # 创建两列布局
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.markdown(f"[👉 点击此处访问授权页面]({auth_url})")
                    st.caption("记得右键在新标签页中打开 ↗")
                
                with col2:
                    redirect_url = st.text_input(
                        "请输入重定向URL：",
                        help="从浏览器地址栏复制整个URL（包含code参数）"
                    )
                    
                if redirect_url:
                    try:
                        # 从URL中提取授权码
                        parsed_url = urlparse(redirect_url)
                        code = parse_qs(parsed_url.query)['code'][0]
                        
                        flow.fetch_token(code=code)
                        self.creds = flow.credentials
                        st.session_state.oauth_credentials = self.creds
                        st.success("认证成功！页面将在3秒后刷新...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"认证失败：{str(e)}")
                        st.error("""
                        请检查：
                        1. URL是否完整复制
                        2. URL中是否包含code参数
                        3. 授权码是否已过期（授权码只能使用一次）
                        
                        如果问题持续，请尝试重新获取新的授权码。
                        """)
                return
            
            # 保存到session state
            st.session_state.oauth_credentials = self.creds
    
    def get_user_email(self) -> Optional[str]:
        """获取用户的Gmail地址"""
        if not self.creds:
            return None
        
        # 如果session state中已经有email，直接返回
        if 'user_email' in st.session_state:
            return st.session_state.user_email
        
        import requests
        try:
            response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {self.creds.token}'}
            )
            response.raise_for_status()  # 抛出HTTP错误
            
            email = response.json().get('email')
            if email:
                st.session_state.user_email = email
                return email
        except Exception as e:
            st.error(f"获取用户信息失败：{str(e)}")
        return None

def login_required(func):
    """装饰器：要求用户登录"""
    def wrapper(*args, **kwargs):
        if not st.session_state.get("authenticated", False):
            # 如果有保存的凭据，尝试自动登录
            if 'oauth_credentials' in st.session_state and 'user_email' in st.session_state:
                auth_manager = GoogleAuthManager()
                email = st.session_state.user_email
                if email in ALLOWED_EMAILS:
                    st.session_state.authenticated = True
                    return func(*args, **kwargs)
            
            st.warning("请使用Google账号登录")
            show_login_page()
            return
        return func(*args, **kwargs)
    return wrapper

def init_auth():
    """初始化认证系统"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    # 本地开发环境自动登录
    if is_local_env():
        if not st.session_state.authenticated:
            st.session_state.authenticated = True
            st.session_state.user_email = st.secrets["google_oauth"]["allowed_emails"][0]  # 使用第一个允许的邮箱
            st.success(f"本地开发环境：已自动以 {st.session_state.user_email} 登录")
        return True
    
    # 生产环境正常的认证流程
    if not st.session_state.authenticated and 'oauth_credentials' in st.session_state:
        auth_manager = GoogleAuthManager()
        email = auth_manager.get_user_email()
        
        if email and email in ALLOWED_EMAILS:
            st.session_state.authenticated = True
            st.session_state.user_email = email
            return True
    
    if not st.session_state.authenticated:
        show_login_page()
        return False
    
    return True

def show_login_page():
    """显示登录页面"""
    # 本地开发环境跳过登录页面
    if is_local_env():
        return
    
    st.title("登录")
    
    # 尝试从session state自动登录
    if 'oauth_credentials' in st.session_state and 'user_email' in st.session_state:
        auth_manager = GoogleAuthManager()
        email = auth_manager.get_user_email()
        
        if email and email in ALLOWED_EMAILS:
            st.session_state.authenticated = True
            st.session_state.user_email = email
            st.success(f"欢迎回来，{email}!")
            st.rerun()
            return
    
    st.write("请使用允许的Google账号登录")
    
    auth_manager = GoogleAuthManager()
    email = auth_manager.get_user_email()
    
    if email:
        if email in ALLOWED_EMAILS:
            st.session_state.authenticated = True
            st.session_state.user_email = email
            st.success(f"欢迎回来，{email}!")
            st.rerun()
        else:
            st.error("抱歉，您的Google账号未被授权使用此应用。")

def show_setup_instructions():
    """显示设置说明"""
    st.markdown("""
    ## 首次设置说明
    
    1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
    2. 创建新项目或选择现有项目
    3. 启用 OAuth 2.0 API
    4. 在凭据页面创建 OAuth 2.0 客户端ID
    5. 将客户端ID和密钥添加到 `.streamlit/secrets.toml` 文件中
    6. 在 Google Cloud Console 中添加允许的重定向URI
    7. 在 secrets.toml 中设置允许的Gmail地址
    
    完成这些步骤后，重启应用即可使用Google登录。
    """) 