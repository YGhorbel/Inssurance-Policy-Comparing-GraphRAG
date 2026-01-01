import os
import torch
import yaml
from threading import Lock
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

load_dotenv()

class LiquidClient:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LiquidClient, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self):
        print("Initializing LiquidAI Client...")
        self.config = self._load_config()
        self.model_id = self.config.get("model_id", "LiquidAI/LFM2-2.6B-Exp") # Default fallback
        self.token = os.environ.get("HF_TOKEN")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        try:
            print(f"Loading model: {self.model_id} on {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, token=self.token)
            
            # Use explicit device placement to avoid meta tensor issues
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                token=self.token,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                low_cpu_mem_usage=True,
            )
            
            # Move model to GPU explicitly
            if self.device == "cuda":
                self.model = self.model.to("cuda")
            
            self.pipe = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                max_new_tokens=512,  # Reduced to avoid OOM
                device=0 if self.device == "cuda" else -1
            )
            print("LiquidAI Model loaded successfully.")
        except Exception as e:
            print(f"Failed to load LiquidAI model: {e}")
            self.pipe = None

    def _load_config(self):
        # Fallback if config file doesn't exist or is different structure
        try:
            with open("configs/config.yaml", "r") as f:
                return yaml.safe_load(f).get("models", {})
        except Exception:
            return {}

    def generate(self, prompt: str, max_new_tokens=1024, do_sample=False) -> str:
        if not self.pipe:
            return "Error: Model not initialized."
        
        try:
            outputs = self.pipe(
                prompt,
                max_new_tokens=max_new_tokens,
                do_sample=do_sample,
                return_full_text=False
            )
            return outputs[0]['generated_text']
        except Exception as e:
            print(f"Generation error: {e}")
            return ""

# Simple singleton access
def get_llm_client():
    return LiquidClient()
