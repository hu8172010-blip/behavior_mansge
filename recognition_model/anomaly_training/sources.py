from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatasetSource:
    key: str
    homepage: str
    method: str
    locator: str
    research_use_note: str


SOURCES = {
    "rlvs": DatasetSource(
        key="rlvs",
        homepage="https://www.kaggle.com/datasets/mohamedmustafa/real-life-violence-situations-dataset",
        method="kaggle",
        locator="mohamedmustafa/real-life-violence-situations-dataset",
        research_use_note="Public research dataset; preserve the dataset card and attribution.",
    ),
    "urfall": DatasetSource(
        key="urfall",
        homepage="https://fenix.ur.edu.pl/mkepski/ds/uf.html",
        method="kaggle",
        locator="shahliza27/ur-fall-detection-dataset",
        research_use_note=(
            "Traceable mirror of UR Fall RGB camera-0 sequences. The mirror declares "
            "no license; use only for academic research and retain the official project attribution."
        ),
    ),
    "le2i": DatasetSource(
        key="le2i",
        homepage="https://zenodo.org/records/17170592",
        method="http",
        locator="https://zenodo.org/records/17170592/files/LE2I.zip?download=1",
        research_use_note=(
            "Research benchmark copy in the OmniFall-derived Zenodo record; retain the "
            "original Le2i citation and the Zenodo record metadata."
        ),
    ),
    "avenue": DatasetSource(
        key="avenue",
        homepage="https://www.cse.cuhk.edu.hk/~leojia/projects/detectabnormal/dataset.html",
        method="http",
        locator="https://www.cse.cuhk.edu.hk/~leojia/projects/detectabnormal/Avenue_Dataset.zip",
        research_use_note="Official CUHK academic benchmark download; retain the ICCV 2013 citation.",
    ),
    "avenue_ground_truth": DatasetSource(
        key="avenue_ground_truth",
        homepage="https://www.cse.cuhk.edu.hk/~leojia/projects/detectabnormal/dataset.html",
        method="http",
        locator="https://www.cse.cuhk.edu.hk/~leojia/projects/detectabnormal/ground_truth_demo.zip",
        research_use_note="Official CUHK spatial ground truth; retain the ICCV 2013 citation.",
    ),
    "iitb_corridor_train": DatasetSource(
        key="iitb_corridor_train",
        homepage="https://rodrigues-royston.github.io/Multi-timescale_Trajectory_Prediction/",
        method="gdrive",
        locator="1HZZjINXIgWnq1FYuVTTBsfJiWsXy1uU5",
        research_use_note="Research purposes only; archive password tb7bdEZE.",
    ),
    "iitb_corridor_test": DatasetSource(
        key="iitb_corridor_test",
        homepage="https://rodrigues-royston.github.io/Multi-timescale_Trajectory_Prediction/",
        method="gdrive",
        locator="1F0m6kRcVKAvDIhGLgOY4QJ-oFdTmkzPI",
        research_use_note="Research purposes only; archive password tb7bdEZE.",
    ),
}
