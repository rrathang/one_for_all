import httpx
from openai import OpenAI

# from .NokiaGPT_ToolOrchestrator import ToolOrchestrator # Assumes this exists in the same package

class Client:
    def __init__(self):
        self.LLMGW_API_KEY = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJ1c2VyTmFtZSI6IkNvcmVJUVRvb2wiLCJPYmplY3RJRCI6IkMxOUJCNzY5LTdGODMt"
            "NDU5RC1CQzExLTY3RjRCNkRGMDI5MSIsIndvcmtTcGFjZU5hbWUiOiJWUjIyOTFDb3Jl"
            "SVEiLCJuYmYiOjE3NTk3MjQyNjksImV4cCI6MTc5MTI2MDI2OSwiaWF0IjoxNzU5NzI0MjY5fQ."
            "luGujL-TvCbSXWxclpPbblsgD0QFRq8KQmOBJdEv4GA"
        )
        self.LLMGW_WORKSPACE = "VR2291CoreIQ"
        self.LLMGW_API_BASE = (
            "https://llmgateway-qa-api.nokia.com/v1.2/"
            # "https://nvdc-prod-euw-llmapiorchestration-app.azurewebsites.net/v1.2/"
        )

        # Initialize LLM client with gateway headers
        self.llm = OpenAI(
            api_key="NONE",
            base_url=self.LLMGW_API_BASE,
            http_client=httpx.Client(
                headers={
                    "api-key": self.LLMGW_API_KEY,
                    "workspacename": self.LLMGW_WORKSPACE,
                }
            ),
        )
    def get_gpt_response(self, prompt: str, model: str = "gpt-5"):
        """
        Executes a chat completion using the given prompt (which should already include
        any system or user context such as ReAct templates).
        """

        response = self.llm.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )
        return response.choices[0].message.content

