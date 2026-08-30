import os
from tempfile import TemporaryDirectory
from unittest import TestCase


class TestRefactorSlurmDataGenerationStep(TestCase):
    def test_refactor_slurm_data_generation_step_no_data_generation(self):
        # A master script without a data generation step should be returned unchanged
        # and the function should return None
        original = """#!/bin/bash
#SBATCH --time=00:10:00

jid1=($(sbatch --nodes=1 --job-name=test_data0_analysis --output=log_data_analysis/test_data0_analysis.out --error=log_data_analysis/test_data0_analysis.err ./submit/test_data0_analysis.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids
"""
        with TemporaryDirectory() as td:
            script = os.path.join(td, "master.sh")
            with open(script, "w") as f:
                f.write(original)

            from core.submit import refactor_slurm_data_generation_step

            result = refactor_slurm_data_generation_step(script)

            self.assertIsNone(result)

            with open(script) as f:
                self.assertEqual(f.read(), original)

    def test_refactor_slurm_data_generation_step_removes_data_generation(self):
        # A master script with a data generation step should have the data generation
        # command returned, and the script rewritten without the data generation job,
        # its echo, and the dependency on it
        original = """#!/bin/bash
#SBATCH --time=00:10:00

jid0=($(sbatch --nodes=1 --job-name=test_data0_generation --output=log_data_generation/test_data0_generation.out --error=log_data_generation/test_data0_generation.err ./submit/test_data0_generation.sh))

echo "jid0 ${jid0[-1]}" >> ./submit/slurm_ids

jid1=($(sbatch --nodes=1 --job-name=test_data0_analysis --dependency=afterok:${jid0[-1]} --output=log_data_analysis/test_data0_analysis.out --error=log_data_analysis/test_data0_analysis.err ./submit/test_data0_analysis.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids
"""
        expected = """#!/bin/bash
#SBATCH --time=00:10:00

jid1=($(sbatch --nodes=1 --job-name=test_data0_analysis  --output=log_data_analysis/test_data0_analysis.out --error=log_data_analysis/test_data0_analysis.err ./submit/test_data0_analysis.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids
"""
        with TemporaryDirectory() as td:
            script = os.path.join(td, "master.sh")
            with open(script, "w") as f:
                f.write(original)

            from core.submit import refactor_slurm_data_generation_step

            result = refactor_slurm_data_generation_step(script)

            self.assertEqual(
                result,
                "jid0=($(sbatch --nodes=1 --job-name=test_data0_generation --output=log_data_generation/test_data0_generation.out --error=log_data_generation/test_data0_generation.err ./submit/test_data0_generation.sh))\n",
            )

            with open(script) as f:
                self.assertEqual(f.read(), expected)
