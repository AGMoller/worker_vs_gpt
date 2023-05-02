"""Command-line interface."""
import hydra
import numpy as np
import torch
from dotenv import load_dotenv
from hydra.core.config_store import ConfigStore
import random

from worker_vs_gpt.data_processing import (
    dataclass_hate_speech,
    dataclass_sentiment,
    dataclass_ten_dim,
    dataclass_analyse_tal,
)

from worker_vs_gpt.config import (
    ANALYSE_TAL_DATA_DIR,
    HATE_SPEECH_DATA_DIR,
    SENTIMENT_DATA_DIR,
    TEN_DIM_DATA_DIR,
)

import wandb
from worker_vs_gpt.config import SetfitParams

from worker_vs_gpt.classification.setfit_trainer import SetFitClassificationTrainer

load_dotenv()

cs = ConfigStore.instance()
cs.store(name="config", node=SetfitParams)

# Set random seeds
torch.manual_seed(42)
np.random.seed(42)
random.seed(42)


# @click.command()
# @click.version_option()
@hydra.main(version_base=None, config_path="conf", config_name="config_setfit.yaml")
def main(cfg: SetfitParams) -> None:
    """Ten Social Dim. SetFit Classification."""

    print(cfg)

    dataset = dataclass_ten_dim.SocialDataset(TEN_DIM_DATA_DIR / "train.json")
    test_dataset = dataclass_ten_dim.SocialDataset(TEN_DIM_DATA_DIR / "test.json")
    base_dataset = dataclass_ten_dim.SocialDataset(TEN_DIM_DATA_DIR / "base.json")
    augmented_dataset = dataclass_ten_dim.SocialDataset(
        TEN_DIM_DATA_DIR / f"{cfg.sampling}_{cfg.augmentation_model}_augmented.json",
        is_augmented=True,
    )

    dataset.data["test"] = test_dataset.data["train"]
    dataset.data["base"] = base_dataset.data["train"]
    dataset.data["original_train"] = dataset.data["train"]
    dataset.data["augmented_train"] = augmented_dataset.data["train"]

    dataset.preprocess(model_name=cfg.ckpt)

    # We have to map the augmented data to the same name as the original data (SetFit only works with one name)
    dataset.data["augmented_train"] = dataset.data["augmented_train"].map(
        lambda x: {"h_text": x["augmented_h_text"]}
    )

    # Specify the length of train and validation set
    validation_length = 750

    dataset.prepare_dataset_setfit(
        cfg.experiment_type, validation_length=validation_length
    )

    # prepare dataset

    model = SetFitClassificationTrainer(dataset=dataset, config=cfg)

    model.train()

    model.test()

    wandb.finish()


if __name__ == "__main__":
    main()  # pragma: no cover