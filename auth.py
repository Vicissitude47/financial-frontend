import streamlit as st
import json
import os
import sys
import logging
import pickle
import base64
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 配置日志记录
logger = logging.getLogger(__name__)

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
        # 检查主机名
        import socket
        hostname = socket.gethostname()
        logger.info(f"Current hostname: {hostname}")
        
        # 如果主机名是 localhost，认为是云环境
        if hostname == "localhost":
            logger.info("Cloud environment detected via hostname")
            return False
            
        # 本地环境的判断条件
        is_local = (
            hostname.startswith("DESKTOP-") or  # Windows 桌面主机名
            hostname.startswith("MacBook")      # Mac 主机名
        )
        
        logger.info(f"Environment detection result: {'local' if is_local else 'cloud'}")
        return is_local
        
    except Exception as e:
        logger.error(f"Error in environment detection: {str(e)}")
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
    # 获取当前应用的URL
    app_url = st.secrets["google_oauth"]["redirect_uri"].split("/oauth2callback")[0]
    
    flow = InstalledAppFlow.from_client_config(
        client_config,
        SCOPES,
        redirect_uri=app_url  # 直接使用应用的根URL
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
                        "redirect_uris": [st.secrets["google_oauth"]["redirect_uri"].split("/oauth2callback")[0]],  # 使用应用根URL
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                }
                
                auth_url, flow = get_auth_url(client_config)
                
                # 显示授权说明
                st.markdown("""
                ### 使用 Google 账号登录
                
                点击下方按钮使用 Google 账号登录。只有授权的邮箱地址可以访问此应用。
                """)
                
                # 使用单列布局，让按钮更显眼
                st.markdown(f"""
                <a href="{auth_url}" target="_blank">
                    <div style="
                        display: inline-block;
                        padding: 0.5em 1em;
                        color: white;
                        background-color: #4285f4;
                        border-radius: 4px;
                        text-decoration: none;
                        margin: 1em 0;
                        cursor: pointer;
                        ">
                        <img src="https://www.google.com/favicon.ico" style="
                            height: 1.2em;
                            margin-right: 0.5em;
                            vertical-align: middle;
                            ">
                        使用 Google 账号登录
                    </div>
                </a>
                """, unsafe_allow_html=True)
                
                # 检查URL中是否包含授权码
                if 'code' in st.query_params:
                    try:
                        code = st.query_params['code']
                        flow.fetch_token(code=code)
                        self.creds = flow.credentials
                        st.session_state.oauth_credentials = self.creds
                        st.success("认证成功！页面将在3秒后刷新...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"认证失败：{str(e)}")
                        st.error("请重新尝试登录。")
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

def save_auth_to_cookie(creds: Credentials, email: str):
    """将认证信息保存到cookie"""
    try:
        # 序列化凭据
        creds_bytes = pickle.dumps(creds)
        creds_b64 = base64.b64encode(creds_bytes).decode('utf-8')
        
        # 设置cookie，7天过期
        cookie_expiry = (datetime.now() + timedelta(days=7)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        st.markdown(f"""
            <script type="text/javascript">
                document.cookie = "auth_creds={creds_b64}; expires={cookie_expiry}; path=/";
                document.cookie = "auth_email={email}; expires={cookie_expiry}; path=/";
            </script>
        """, unsafe_allow_html=True)
        logger.info("Auth credentials saved to cookie")
    except Exception as e:
        logger.error(f"Failed to save auth to cookie: {str(e)}")

def load_auth_from_cookie() -> Tuple[Optional[Credentials], Optional[str]]:
    """从cookie加载认证信息"""
    try:
        # 获取cookie
        cookies = dict(item.split("=") for item in st.experimental_get_query_params().get("cookie", [""])[0].split("; "))
        
        if "auth_creds" in cookies and "auth_email" in cookies:
            # 反序列化凭据
            creds_b64 = cookies["auth_creds"]
            creds_bytes = base64.b64decode(creds_b64)
            creds = pickle.loads(creds_bytes)
            
            email = cookies["auth_email"]
            logger.info("Auth credentials loaded from cookie")
            return creds, email
    except Exception as e:
        logger.error(f"Failed to load auth from cookie: {str(e)}")
    
    return None, None

def init_auth():
    """初始化认证系统"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    # 本地开发环境自动登录
    if is_local_env():
        if not st.session_state.authenticated:
            st.session_state.authenticated = True
            st.session_state.user_email = st.secrets["google_oauth"]["allowed_emails"][0]
            logger.info("Auto-login in local environment")
        return True
    
    # 尝试从cookie恢复会话
    if not st.session_state.authenticated:
        creds, email = load_auth_from_cookie()
        if creds and email and email in ALLOWED_EMAILS:
            st.session_state.oauth_credentials = creds
            st.session_state.user_email = email
            st.session_state.authenticated = True
            logger.info("Session restored from cookie")
            return True
    
    # 生产环境正常的认证流程
    if not st.session_state.authenticated and 'oauth_credentials' in st.session_state:
        auth_manager = GoogleAuthManager()
        email = auth_manager.get_user_email()
        
        if email and email in ALLOWED_EMAILS:
            st.session_state.authenticated = True
            st.session_state.user_email = email
            # 保存认证信息到cookie
            save_auth_to_cookie(auth_manager.creds, email)
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