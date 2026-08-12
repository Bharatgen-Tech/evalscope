# Copyright (c) Alibaba, Inc. and its affiliates.

import os
from typing import Any, Dict

from evalscope.api.benchmark import BenchmarkMeta, MultiChoiceAdapter
from evalscope.api.dataset import Sample
from evalscope.api.registry import register_benchmark
from evalscope.constants import Tags
from evalscope.utils.logger import get_logger
from evalscope.utils.multi_choices import MultipleChoiceTemplate

logger = get_logger()


@register_benchmark(
    BenchmarkMeta(
        name='hellaswag_hi',
        pretty_name='HellaSwag-Hindi',
        tags=[Tags.REASONING, Tags.MULTIPLE_CHOICE],
        description="""
## Overview

HellaSwag-Hindi is a Hindi translation of the HellaSwag commonsense sentence-completion benchmark's
full validation set. The context stem stays in English; the 4 candidate continuations are translated
into Hindi, so the model must connect an English scenario to its most plausible Hindi-phrased ending.

## Task Description

- **Task Type**: Commonsense Sentence Completion (mixed-language)
- **Input**: An English context sentence with 4 Hindi-language candidate continuations
- **Output**: Correct answer letter
- **Coverage**: Full HellaSwag validation set (10,042 examples)

## Evaluation Notes

- Default configuration uses **0-shot** evaluation (test split, the only split available)
- Ships as data bundled with this adapter (not hosted on HuggingFace/ModelScope)
""",
        dataset_id=os.path.join(os.path.dirname(__file__), 'data'),
        metric_list=['acc'],
        subset_list=['Hindi'],
        few_shot_num=0,
        train_split=None,
        eval_split='test',
        prompt_template=MultipleChoiceTemplate.SINGLE_ANSWER,
    )
)
class HellaSwagHiAdapter(MultiChoiceAdapter):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def load_from_disk(self, **kwargs):
        return super().load_from_disk(use_local_loader=True)

    def record_to_sample(self, record: Dict[str, Any]) -> Sample:
        target_letter = chr(ord('A') + int(record['gold']))

        return Sample(
            input=record['query'],
            choices=record['choices'],
            target=target_letter,
        )
