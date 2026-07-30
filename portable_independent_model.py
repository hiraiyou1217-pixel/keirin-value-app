from __future__ import annotations

import math
from typing import Any, Iterable, Sequence


PORTABLE_MODEL_FORMAT = "keirin_hgb_binary_v1"


def _python_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()

    return value


def export_hist_gradient_boosting_package(
    package: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(package, dict):
        raise RuntimeError(
            "モデルパッケージの形式が不正です。"
        )

    if not package.get("odds_independent"):
        raise RuntimeError(
            "オッズ非依存モデルではありません。"
        )

    model = package.get("model")
    feature_columns = list(
        package.get("feature_columns", [])
    )

    if model is None or not feature_columns:
        raise RuntimeError(
            "モデル本体または特徴量一覧がありません。"
        )

    classes = [
        _python_scalar(value)
        for value in list(
            getattr(model, "classes_", [])
        )
    ]

    if classes != [0, 1]:
        raise RuntimeError(
            "端末版へ変換できるのは"
            "クラス[0, 1]の二値モデルだけです。"
        )

    baseline_values = getattr(
        model,
        "_baseline_prediction",
        None,
    )
    predictor_groups = getattr(
        model,
        "_predictors",
        None,
    )

    if (
        baseline_values is None
        or predictor_groups is None
    ):
        raise RuntimeError(
            "対応していない学習モデル形式です。"
        )

    baseline = float(
        baseline_values.ravel()[0]
    )
    trees: list[list[list[Any]]] = []

    for iteration, group in enumerate(
        predictor_groups,
        start=1,
    ):
        if len(group) != 1:
            raise RuntimeError(
                "多クラス決定木は端末版へ"
                f"変換できません: iteration={iteration}"
            )

        nodes = getattr(group[0], "nodes", None)

        if nodes is None:
            raise RuntimeError(
                "決定木ノードを取得できません。"
            )

        tree: list[list[Any]] = []

        for node_index, node in enumerate(nodes):
            if int(node["is_categorical"]):
                raise RuntimeError(
                    "カテゴリ分岐を含むモデルは"
                    "端末版へ変換できません: "
                    f"tree={iteration} node={node_index}"
                )

            tree.append(
                [
                    float(node["value"]),
                    int(node["feature_idx"]),
                    float(node["num_threshold"]),
                    bool(node["missing_go_to_left"]),
                    int(node["left"]),
                    int(node["right"]),
                    bool(node["is_leaf"]),
                ]
            )

        trees.append(tree)

    metadata_keys = (
        "model_version",
        "model_type",
        "trained_at",
        "training_start_date",
        "training_end_date",
        "training_cutoff_date",
        "excluded_after_cutoff_race_count",
        "race_count",
        "row_count",
        "feature_coverage",
    )
    metadata = {
        key: package.get(key)
        for key in metadata_keys
    }

    return {
        "format": PORTABLE_MODEL_FORMAT,
        "odds_independent": True,
        "classes": classes,
        "positive_class": 1,
        "feature_columns": feature_columns,
        "feature_count": len(feature_columns),
        "baseline": baseline,
        "trees": trees,
        "tree_count": len(trees),
        "metadata": metadata,
    }


def _tree_value(
    tree: Sequence[Sequence[Any]],
    row: Sequence[float],
) -> float:
    node_index = 0

    while True:
        node = tree[node_index]

        if bool(node[6]):
            return float(node[0])

        feature_index = int(node[1])

        if feature_index >= len(row):
            raise RuntimeError(
                "端末モデルの特徴量位置が範囲外です。"
            )

        value = float(row[feature_index])

        if math.isnan(value):
            go_left = bool(node[3])
        else:
            go_left = value <= float(node[2])

        node_index = int(
            node[4] if go_left else node[5]
        )


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)

    positive = math.exp(value)
    return positive / (1.0 + positive)


def predict_positive_probabilities(
    portable_model: dict[str, Any],
    rows: Iterable[Sequence[float]],
) -> list[float]:
    if (
        portable_model.get("format")
        != PORTABLE_MODEL_FORMAT
    ):
        raise RuntimeError(
            "端末モデルの形式が不正です。"
        )

    feature_count = int(
        portable_model.get(
            "feature_count",
            0,
        )
    )
    baseline = float(
        portable_model.get("baseline", 0.0)
    )
    trees = portable_model.get("trees")

    if (
        feature_count <= 0
        or not isinstance(trees, list)
        or not trees
    ):
        raise RuntimeError(
            "端末モデルの内容が不足しています。"
        )

    output: list[float] = []

    for row in rows:
        if len(row) != feature_count:
            raise RuntimeError(
                "端末モデルへ渡した特徴量数が"
                "一致しません。"
            )

        raw_value = baseline

        for tree in trees:
            raw_value += _tree_value(
                tree,
                row,
            )

        output.append(_sigmoid(raw_value))

    return output
