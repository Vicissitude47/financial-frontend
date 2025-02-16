import streamlit as st
import json
import os
from typing import Optional, Dict, Tuple
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from pathlib import Path

# 配置
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

# 从Streamlit secrets获取配置
ALLOWED_EMAILS = set(st.secrets["google_oauth"]["allowed_emails"])

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
                self.creds.refresh(Request())
            else:
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
                
                flow = InstalledAppFlow.from_client_config(
                    client_config,
                    SCOPES,
                    redirect_uri=st.secrets["google_oauth"]["redirect_uri"]
                )
                
                try:
                    self.creds = try_port(flow)
                    if not self.creds:
                        st.error("无法启动认证服务器，请检查端口是否被占用。")
                        return
                except Exception as e:
                    st.error(f"认证过程出错: {str(e)}")
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
        response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {self.creds.token}'}
        )
        
        if response.status_code == 200:
            email = response.json().get('email')
            # 保存email到session state
            if email:
                st.session_state.user_email = email
            return email
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

def show_login_page():
    """显示登录页面"""
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
    
    if st.button("使用Google账号登录"):
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
        else:
            st.error("登录失败，请重试。")

def init_auth():
    """初始化认证系统"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    # 如果未登录，尝试自动登录
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