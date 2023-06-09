import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Union
import torch
import pandas as pd
from numpy import random
from worker_vs_gpt.config import TEN_DIM_DATA_DIR

rng = random.RandomState(42)

from worker_vs_gpt.prompting.langchain_prompting import DataTemplates

from langchain.llms import HuggingFacePipeline
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from peft import PeftModelForCausalLM


def get_device() -> torch.device:
    """Get device."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.has_mps:
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    print(f"Using device: {device}")

    return device


def read_json(path: Path) -> List[Dict[str, Union[str, int]]]:
    with open(path, "r") as f:
        data: List[Dict[str, Union[str, int]]] = json.load(f)
    return data


def save_json(path: Path, container: Iterable) -> None:
    """write dict to path."""
    print(f"Saving json to {path}")
    with open(path, "w") as outfile:
        json.dump(container, outfile, ensure_ascii=False, indent=4)


class LabelMatcher:
    """For label consistency in zero-shot classification."""

    def __init__(self, labels: List[str], task: str = "ten-dim"):
        self.labels = labels
        self.task = task
        self._assert_task()

    def __call__(self, label: str, text: str) -> str:
        if self.task == "ten-dim":
            for true_label in self.labels:
                if label.lower() in true_label.lower():
                    return true_label
            print(f"Label not found: {label}, for text: {text}")
            return "neutral"

        if self.task == "hate-speech":
            if label.lower() == "off":
                return "OFF"
            elif label.lower() == "not":
                return "NOT"
            else:
                print(f"Label not found: {label}, for text: {text}")
                return "NOT"

        if self.task == "sentiment":
            if label.lower() == "positive":
                return "positive"
            elif label.lower() == "negative":
                return "negative"
            elif label.lower() == "neutral":
                return "neutral"
            else:
                print(f"Label not found: {label}, for text: {text}")
                return "neutral"

    def _assert_task(self):
        if self.task not in ["ten-dim", "hate-speech", "sentiment"]:
            raise ValueError(f"Task not found: {self.task}")


def parse_output(input_string: str) -> List[str]:
    input_list = input_string.split("\n")  # split the input by newline characters
    output_list = []
    for item in input_list:
        item = item.lstrip(
            "0123456789. "
        )  # remove enumeration and any leading whitespace
        if item:  # skip empty items
            output_list.append(item)
    return output_list


def balanced_sample_df(df: pd.DataFrame, n: int) -> pd.DataFrame:
    class_counts = df["target"].value_counts()
    min_samples_per_class = class_counts.min()
    num_classes = class_counts.size
    samples_per_class = n // num_classes

    sampled_indices = []
    for label in class_counts.index:
        indices = df.index[df["target"] == label]
        if class_counts[label] >= samples_per_class:
            sampled_indices.extend(
                rng.choice(indices, size=samples_per_class, replace=False)
            )
        else:
            sampled_indices.extend(
                rng.choice(indices, size=samples_per_class, replace=True)
            )

    df_sampled = df.loc[sampled_indices]
    remaining_samples = n - df_sampled.shape[0]
    if remaining_samples > 0:
        remaining_indices = df.index.difference(df_sampled.index)
        remaining_samples_df = df.loc[
            rng.choice(remaining_indices, size=remaining_samples)
        ]
        df_sampled = pd.concat([df_sampled, remaining_samples_df])

    return df_sampled.sample(frac=1, random_state=rng).reset_index(drop=True)


def get_class_count_needed(df: pd.DataFrame, n: int = 5000) -> Dict[str, int]:
    """This function returns a dictionary of class counts needed to balance a dataset."""
    n_classes = df["target"].nunique()
    n_per_class = n // n_classes
    class_counts = df["target"].value_counts()

    class_counts_needed = n_per_class / class_counts

    # Round up to nearest integer
    class_counts_needed = class_counts_needed.apply(lambda x: int(x) + 1)

    return class_counts_needed.to_dict()


def get_pipeline(model_id: str, lora_wieghts_path: str) -> HuggingFacePipeline:
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id)
    added_tokens = tokenizer.add_special_tokens(
        {"bos_token": "<s>", "eos_token": "</s>", "pad_token": "<pad>"}
    )

    if added_tokens > 0:
        model.resize_token_embeddings(len(tokenizer))

    model = PeftModelForCausalLM.from_pretrained(
        model, lora_wieghts_path, device_map="auto", torch_dtype=torch.float16
    )
    model.to(dtype=torch.float16)

    print(f"Mem needed: {model.get_memory_footprint() / 1024 / 1024 / 1024:.2f} GB")

    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer, max_new_tokens=10
    )
    hf = HuggingFacePipeline(pipeline=pipe)

    return hf


if __name__ == "__main__":
    augmentation_templates = DataTemplates()

    text = "h_text"  # text column (can be text or h_text)
    dataset = pd.read_json(os.path.join(TEN_DIM_DATA_DIR, "base.json"))
    augmentation_prompt = augmentation_templates.get_ten_dim_prompt()
    label_to_description = {
        "knowledge": "Exchange of ideas or information",
        "power": "Having power over the behavior and outcomes of another",
        "status": "Conferring status, appreciation, gratitude, or admiration upon another",
        "trust": "Will of relying on the actions or judgments of another",
        "social_support": "Giving emotional or practical aid and companionship",
        "similarity_identity": "Shared interests, motivations, outlooks or Shared sense of belonging to the same community or group",
        "fun": "Experiencing leisure, laughter, and joy",
        "conflict": "Contrast or diverging views",
        "neutral": "neutral communication",
    }

    balance_generation_df(dataset, n=5000)
