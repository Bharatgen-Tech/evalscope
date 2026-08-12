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

OPTION_KEYS = ['option1', 'option2', 'option3', 'option4']

SUBSET_LIST = ['association', 'country', 'gk', 'states']


@register_benchmark(
    BenchmarkMeta(
        name='sanskriti',
        pretty_name='Sanskriti',
        tags=[Tags.KNOWLEDGE, Tags.MULTIPLE_CHOICE],
        description="""
## Overview

Sanskriti is a multiple-choice trivia benchmark testing knowledge of Indian states' culture, history,
and geography, sourced from state-specific attributes (art, cuisine, festivals, etc.) with
Wikipedia-backed answers.

## Task Description

- **Task Type**: Multiple-Choice Trivia Question Answering
- **Input**: A question about a specific Indian state's culture/geography/history, with 4 answer choices
- **Output**: Correct answer letter
- **Subsets**: `association` (state-attribute association trivia), `country` (country-level trivia),
  `gk` (general knowledge), `states` (state-identification trivia)

## Evaluation Notes

- Default configuration uses **0-shot** evaluation (test split, the only split available)
- Questions and choices are in English
- Ships as data bundled with this adapter (not hosted on HuggingFace/ModelScope)
""",
        dataset_id=os.path.join(os.path.dirname(__file__), 'data'),
        metric_list=['acc'],
        subset_list=SUBSET_LIST,
        few_shot_num=0,
        train_split=None,
        eval_split='test',
        prompt_template=MultipleChoiceTemplate.SINGLE_ANSWER,
    )
)
class SanskritiAdapter(MultiChoiceAdapter):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def load_from_disk(self, **kwargs):
        return super().load_from_disk(use_local_loader=True)

    def record_to_sample(self, record: Dict[str, Any]) -> Sample:
        choices = [record[key] for key in OPTION_KEYS]
        target_index = choices.index(record['answer'])
        target_letter = chr(ord('A') + target_index)

        return Sample(
            input=record['question'],
            choices=choices,
            target=target_letter,
            metadata={
                'state': record.get('state', ''),
                'attribute': record.get('attribute', ''),
            },
        )
