import os
import yaml
import torch
from dotenv import load_dotenv
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig
)

load_dotenv()

# Global cache (CLI mode)
_CLI_MODEL = None
_CLI_TOKENIZER = None


def get_streamlit_cache():
    try:
        import streamlit as st
        return st.cache_resource
    except ImportError:
        return lambda x: x


@get_streamlit_cache()
def load_model_cached(model_id, token):
    print(f"Loading model: {model_id}")

    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        token=token,
        trust_remote_code=True
    )
    
    # 4-bit quantization for efficiency on laptop GPU
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4"
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        device_map="auto",
        quantization_config=bnb_config,
        token=token,
        trust_remote_code=True
    )

    print("Model loaded successfully.")
    return model, tokenizer


class FHClient:
    def __init__(self, config_path="configs/config.yaml"):
        global _CLI_MODEL, _CLI_TOKENIZER
        
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)["models"]

        self.token = os.getenv("HF_TOKEN") or cfg.get("hf_token")
        # Update default to LiquidAI/LFM2-2.6B-Exp
        self.model_id = cfg.get(
            "model_id",
            "LiquidAI/LFM2-2.6B-Exp"
        )

        try:
            import streamlit  # noqa
            is_streamlit = True
        except ImportError:
            is_streamlit = False

        if is_streamlit:
            self.model, self.tokenizer = load_model_cached(self.model_id, self.token)
        else:
            if _CLI_MODEL is None:
                _CLI_MODEL, _CLI_TOKENIZER = load_model_cached(self.model_id, self.token)
            self.model, self.tokenizer = _CLI_MODEL, _CLI_TOKENIZER

    def generate(self, prompt: str, max_new_tokens=1024, temperature=0.1):
        if not self.model or not self.tokenizer:
            raise RuntimeError("Model/Tokenizer not initialized")

        messages = [
            {"role": "user", "content": prompt},
        ]

        # Tokenize and apply chat template as requested
        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)

        # Generate
        outputs = self.model.generate(
            **inputs, 
            max_new_tokens=max_new_tokens,
            pad_token_id=self.tokenizer.eos_token_id 
        )
        
        # Decode only the generated part
        input_length = inputs["input_ids"].shape[-1]
        decoded_output = self.tokenizer.decode(
            outputs[0][input_length:], 
            skip_special_tokens=True
        )
        
        return decoded_output.strip()
