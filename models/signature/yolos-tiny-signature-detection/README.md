---
library_name: transformers
license: apache-2.0
datasets:
- tech4humans/signature-detection
base_model:
- hustvl/yolos-tiny
---

# YOLOS (tiny-sized) Model For Handwritten Signature Detection

YOLOS model finetuned to detect handwritten signatures in document images using [[tech4humans/signature-detection](https://huggingface.co/datasets/huggingface/badges/resolve/main/dataset-on-hf-md.svg)](https://huggingface.co/datasets/tech4humans/signature-detection) dataset.

Original YOLOS was introduced in the paper [You Only Look at One Sequence: Rethinking Transformer in Vision through Object Detection](https://arxiv.org/abs/2106.00666) by Fang et al. and first released in [this repository](https://github.com/hustvl/YOLOS).


## Model description

YOLOS is a Vision Transformer (ViT) trained using the DETR loss. Despite its simplicity, a base-sized YOLOS model is able to achieve 42 AP on COCO validation 2017 (similar to DETR and more complex frameworks such as Faster R-CNN).


- **Finetuned by:** [Mario DEFRANCE](www.linkedin.com/in/mario-defrance)
- **Repository:** [mdefrance/signature-detection](https://github.com/mdefrance/signature-detection/tree/yolos-tiny-signature-detection)
- **Model type:** [YOLOS](https://huggingface.co/docs/transformers/model_doc/yolos)
- **License:** Apache 2.0 license
- **Finetuned from model** [hustvl/yolos-tiny](https://huggingface.co/hustvl/yolos-tiny)


## Uses

This model is designed for detecting handwritten signatures in scanned documents, contracts, or forms.

You can try it instantly in your browser here:
[![HF Space](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-md.svg)](https://huggingface.co/spaces/mdefrance/signature-detection-demo)

### Direct Use

Here is how to use this model:

```python
from datasets import load_dataset
from transformers import pipeline

# Load the tech4humans signature dataset
dataset = load_dataset("samuellimabraz/signature-detection")

# Load the finetuned model
yolos = pipeline(
    task="object-detection",
    model="mdefrance/yolos-tiny-signature-detection",
    device_map="auto",
)

# Inference on test sample
prediction = yolos(dataset["test"][0].get("image"))
```

Currently, both the image processor and model support PyTorch.

### Out-of-Scope Use

- **Fraudulent Use:** This model must not be used for forging signatures or any illegal activity. It’s meant for legitimate signature detection in documents.
- **Other Objects:** Not suitable for detecting non-signature elements in documents.
- **Critical Decisions:** Should not be solely relied on for high-stakes decisions (e.g., legal or financial) without human validation.

## Bias, Risks, and Limitations

- **Bias:** May not generalize well if training data lacks diversity in signature styles or cultural context.
- **Risks:** False positives/negatives can occur, impacting document validation.
- **Limitations:** Performance may degrade on poor-quality images or in challenging visual conditions (e.g., noise, lighting).

### Recommendations

- **Improve Training Data:** Fine-tune with diverse and representative samples to reduce bias.
- **Human Oversight:** Always include a human review step for critical use cases.
- **Image Quality:** Use clean, high-resolution images; apply preprocessing if needed.
- **Ethical Use:** Follow legal and ethical standards, ensuring privacy and responsible deployment.


## Training Details

### Training Data

<table>
  <tr>
    <td style="text-align: center; padding: 10px;">
      <a href="https://huggingface.co/datasets/tech4humans/signature-detection">
        <img src="https://huggingface.co/datasets/huggingface/badges/resolve/main/dataset-on-hf-md-dark.svg" alt="Dataset on HF">
      </a>
    </td>
  </tr>
</table>

The training utilized a dataset built from two public datasets: [Tobacco800](https://paperswithcode.com/dataset/tobacco-800) and [signatures-xc8up](https://universe.roboflow.com/roboflow-100/signatures-xc8up), unified and processed in [Roboflow](https://roboflow.com/).
The processed dataset was created by [Samuel Lima Braz](https://huggingface.co/samuellimabraz), and all credit for the dataset preparation goes to him.

**Dataset Summary:**
- Training: 1,980 images (70%)
- Validation: 420 images (15%)
- Testing: 419 images (15%)
- Format: COCO JSON
- Resolution: 640x640 pixels



### Training Procedure

See [mdefrance/signature-detection](https://github.com/mdefrance/signature-detection/tree/yolos-tiny-signature-detection) for details on training procedure.

#### Metrics

Performances computed on the testing set:

| **Metric**                      | [yolos-base-signature-detection](https://huggingface.co/mdefrance/yolos-base-signature-detection) | [yolos-small-signature-detection](https://huggingface.co/mdefrance/yolos-small-signature-detection) | [yolos-tiny-signature-detection](https://huggingface.co/mdefrance/yolos-tiny-signature-detection) |
|:--------------------------------|------------:|-----------:|-----------------------------:|
| **Inference Time - CPU (s)**    |    2.250    |      0.787 |                   **0.262**  |
| **Inference Time - GPU (s)**    |     1.464   |      0.023 |                   **0.014**  |
| **Parameters**                  |   127.73M   |     30.65M |                        6.47M |
| **mAP50**                       |   **0.887** |      0.859 |                        0.856 |
| **mAP50-95**                    |   **0.495** |      0.419 |                        0.395 |

Inference times are computed on a laptop with following specs:
* CPU: Intel Core i7-9750H
* GPU: NVIDIA GeForce GTX 1650

## License Comparison

### GNU Affero General Public License v3.0 (AGPL-3.0)

AGPL-3.0 is a strong copyleft license designed to keep software and its modifications open-source, especially for web apps and network services.

- **Strong Copyleft**: Modified versions must also be AGPL-licensed.
- **Network Use**: Users must get the source code, even if they only interact with the software over a network.
- **Commercial Use**: Allowed, but any changes must be shared under AGPL-3.0.
- **Patent Protection**: Includes safeguards against patent and trademark claims.

### Apache License 2.0

Apache 2.0 is a permissive license that offers flexibility for both open-source and proprietary use.

- **Permissive**: Modifications and derivatives don’t need to be open-source.
- **Commercial Use**: Fully allowed with no requirement to share changes.
- **Patent Protection**: Includes strong patent clauses.
- **Compatibility**: Easy to combine with other licenses and projects.

### Summary: Why Apache 2.0 Offers More Flexibility

While AGPL-3.0 ensures openness, Apache 2.0 is better suited for businesses and closed-source use:

- No obligation to disclose modified code.
- Easier to integrate into proprietary systems.
- More flexible for commercial applications.

For full license texts, see:
- [GNU AGPL-3.0 License](https://www.gnu.org/licenses/agpl-3.0.html)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)



## Citation

This model is a finetuned version of the YOLOS model introduced in the following paper. If you use this model, please cite the original work:

**BibTeX:**
```bibtex
@article{DBLP:journals/corr/abs-2106-00666,
  author    = {Yuxin Fang and
               Bencheng Liao and
               Xinggang Wang and
               Jiemin Fang and
               Jiyang Qi and
               Rui Wu and
               Jianwei Niu and
               Wenyu Liu},
  title     = {You Only Look at One Sequence: Rethinking Transformer in Vision through
               Object Detection},
  journal   = {CoRR},
  volume    = {abs/2106.00666},
  year      = {2021},
  url       = {https://arxiv.org/abs/2106.00666},
  eprinttype = {arXiv},
  eprint    = {2106.00666},
  timestamp = {Fri, 29 Apr 2022 19:49:16 +0200},
  biburl    = {https://dblp.org/rec/journals/corr/abs-2106-00666.bib},
  bibsource = {dblp computer science bibliography, https://dblp.org}
}
```

### Additional Resources

- **Blog post of comparison of Signature Detection Models:** [Hugging Face Blog](https://huggingface.co/blog/samuellimabraz/signature-detection-model)
- **Blog post associated Finetuning Notebook:** [Google Colab Notebook](https://colab.research.google.com/drive/1wSySw_zwyuv6XSaGmkngI4dwbj-hR4ix)
- **Finetuning of YOLOS Notebook Example:** [Google Colab Notebook](https://colab.research.google.com/github/NielsRogge/Transformers-Tutorials/blob/master/YOLOS/Fine_tuning_YOLOS_for_object_detection_on_custom_dataset_(balloon).ipynb)

## Acknowledgements

This model is finetuned for handwritten signature detection using the [[tech4humans/signature-detection](https://huggingface.co/datasets/huggingface/badges/resolve/main/dataset-on-hf-md.svg)](https://huggingface.co/datasets/tech4humans/signature-detection) Dataset. The finetuning process and additional resources can be found in the GitHub Repository [mdefrance/signature-detection](https://github.com/mdefrance/signature-detection/tree/yolos-tiny-signature-detection).


## **Author**

<div align="center">
  <table>
    <tr>
      <td align="center" width="140">
        <a href="https://huggingface.co/mdefrance">
          <img src="https://avatars.githubusercontent.com/u/74489838?v=4" width="120" alt="Mario DEFRANCE"/>
          <h3>Mario DEFRANCE</h3>
        </a>
        <p><i>Data Scientist / AI Engineer</i></p>
      </td>
      <td width="500">
        <h4>Responsibilities in this Project</h4>
        <ul>
          <li>🔬 Model development and training</li>
          <li>⚙️ Performance evaluation</li>
          <li>📝 Technical documentation and model card</li>
        </ul>
      </td>
    </tr>
  </table>
</div>
