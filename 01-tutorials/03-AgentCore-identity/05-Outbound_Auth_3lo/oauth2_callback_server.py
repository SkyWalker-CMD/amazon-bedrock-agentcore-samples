import argparse
from datetime import timedelta
import time
import uvicorn
import requests
import logging
from bedrock_agentcore.services.identity import IdentityClient, UserTokenIdentifier

from fastapi import FastAPI, HTTPException, status


OAUTH2_CALLBACK_SERVER_PORT = 9090
PING_ENDPOINT = '/ping'
OAUTH2_CALLBACK_ENDPOINT = '/oauth2/callback'
USER_IDENTIFIER_ENDPOINT = '/userIdentifier/token'

logger = logging.getLogger(__name__)


class OAuth2CallbackServer:
    def __init__(self, region: str):
        self.identity_client = IdentityClient(region=region)
        self.user_token_identifier = None
        self.app = FastAPI()
        self._setup_routes()
        
    def _setup_routes(self):
        @self.app.post("/store/token")
        async def _store_user_token(_user_token_identifier: UserTokenIdentifier):
            self.user_token_identifier = _user_token_identifier
        
        @self.app.get(PING_ENDPOINT)
        async def _handle_ping():
            return {"status": "success"}
        
        @self.app.get(OAUTH2_CALLBACK_ENDPOINT)
        async def _handle_oauth2_callback(session_id: str):
            if not session_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="missing session_id query parameter"
                )
            
            if not self.user_token_identifier:
                logger.error('No configured UserToken')
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal Server Error"
                )
            
            self.identity_client.complete_resource_token_auth(
                session_uri=session_id, 
                user_identifier=self.user_token_identifier
            )
            
            return {"message": "completed OAuth2 3LO flow successfully"}
    
    def get_app(self) -> FastAPI:
        return self.app


def get_oauth2_callback_url() -> str:
    return f"http://localhost:{OAUTH2_CALLBACK_SERVER_PORT}{OAUTH2_CALLBACK_ENDPOINT}"


def store_token_in_oauth2_callback_server(user_token: str):
    return requests.post(
        f"http://localhost:{OAUTH2_CALLBACK_SERVER_PORT}{OAUTH2_CALLBACK_ENDPOINT}", 
        json={"user_token": user_token},
        timeout=2
    )


def wait_for_oauth2_server_to_be_ready(duration: timedelta = timedelta(seconds=30)) -> bool:
    logger.info("Waiting for OAuth2 callback server to be ready...")
    timeout_in_seconds = duration.seconds
        
    start_time = time.time()
    while time.time() - start_time < timeout_in_seconds:
        try:
            response = requests.get(f"http://localhost:{OAUTH2_CALLBACK_SERVER_PORT}{PING_ENDPOINT}", timeout=2)
            if response.status_code == status.HTTP_200_OK:
                logger.info("OAuth2 callback server is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        
        time.sleep(2)
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0 and elapsed > 0:
            logger.info(f"Still waiting... ({elapsed}/{timeout_in_seconds}s)")
        
    logger.error(f"Timeout: OAuth2 callback server not ready after {timeout_in_seconds} seconds")
    return False


def main():
    parser = argparse.ArgumentParser(description='OAuth2 Callback Server')
    parser.add_argument(
        "-r",
        "--region",
        type=str,
        required=True,
        help="The AWS region to use (e.g. us-east-1)"
    )
    
    args = parser.parse_args()
    oauth2_callback_server = OAuth2CallbackServer(region=args.region)
    
    uvicorn.run(oauth2_callback_server.get_app(), host='127.0.0.1', port=OAUTH2_CALLBACK_SERVER_PORT)
