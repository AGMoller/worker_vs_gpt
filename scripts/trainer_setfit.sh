#!/bin/bash

#SBATCH --job-name=experiments    # Job name
#SBATCH --output=run_outputs/trainer_setfit.%j.out      # Name of output file (%j expands to jobId)
#SBATCH --cpus-per-task=12       # Schedule one core
#SBATCH --time=16:00:00          # Run time (hh:mm:ss) - run for one hour max
#SBATCH --gres=gpu
#SBATCH --partition=brown,red    # Run on either the Red or Brown queue
#SBATCH --mail-type=BEGIN,FAIL,END    # Send an email when the job finishes or fails
#SBATCH --account=researchers

hostname

nvidia-smi

module load poetry

poetry shell

python -m src.worker_vs_gpt.setfit_classification