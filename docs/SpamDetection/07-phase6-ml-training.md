# Phase 6: ML Model Training

## Overview
- **Duration**: Week 15-18
- **Dependencies**: Phase 5 (Training data collection)
- **Goal**: Train and deploy ML model for spam detection

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Feature Engineering](#2-feature-engineering)
3. [Model Selection](#3-model-selection)
4. [Training Pipeline](#4-training-pipeline)
5. [Model Evaluation](#5-model-evaluation)
6. [Model Deployment](#6-model-deployment)
6.5. [Model Loading Optimization](#65-model-loading-optimization)
7. [Inference Service](#7-inference-service)
8. [Monitoring & Retraining](#8-monitoring--retraining)
9. [Testing Strategy](#9-testing-strategy)
10. [Verification Checklist](#10-verification-checklist)

---

## 1. Prerequisites

### Data Requirements

| Requirement | Minimum | Status Check |
|-------------|---------|--------------|
| SPAM labels | 500 | `SELECT COUNT(*) FROM spam_training_labels WHERE label='SPAM'` |
| LEGITIMATE labels | 500 | `SELECT COUNT(*) FROM spam_training_labels WHERE label='LEGITIMATE'` |
| High confidence (≥0.8) | 80% | Check average confidence |
| Feature coverage | 90% | Labels with features in user_spam_features |

### Python Dependencies

Add to `requirements.txt`:

```txt
scikit-learn>=1.3.0
pandas>=2.0.0
numpy>=1.24.0
joblib>=1.3.0
imbalanced-learn>=0.11.0  # For handling class imbalance
```

### Directory Structure

```
redditrepostsleuth/core/ml/
├── __init__.py
├── spam_model_trainer.py      # Training pipeline
├── spam_model_predictor.py    # Inference service
├── feature_engineering.py     # Feature preprocessing
└── model_evaluator.py         # Evaluation metrics

models/                        # Model storage (gitignored)
├── spam_detector_v1.pkl
├── spam_detector_v1_metadata.json
└── feature_scaler_v1.pkl
```

---

## 2. Feature Engineering

### Feature Selection

Based on importance analysis from rule-based scoring:

**High Importance Features (Always Include)**:
| Feature | Type | Description |
|---------|------|-------------|
| `repost_ratio` | float | Ratio of reposts to total posts |
| `adult_platform_ratio` | float | Ratio of adult platform links |
| `posts_per_day_avg` | float | Posting frequency |
| `karma_farming_sub_posts` | int | Posts in karma farm subs |
| `account_age_days` | int | Account age (Tier 2) |
| `karma_per_day` | float | Karma accumulation rate |

**Medium Importance Features**:
| Feature | Type | Description |
|---------|------|-------------|
| `unique_subreddits_posted` | int | Subreddit diversity |
| `nsfw_post_ratio` | float | NSFW content ratio |
| `short_link_ratio` | float | Promo link ratio |
| `username_suspicious_pattern` | bool | Pattern match |
| `total_karma` | int | Total karma (Tier 2) |
| `comment_karma` | int | Comment karma (Tier 2) |

**Lower Importance (Include If Available)**:
| Feature | Type | Description |
|---------|------|-------------|
| `has_verified_email` | bool | Email verified (Tier 2) |
| `has_custom_avatar` | bool | Custom avatar (Tier 2) |
| `summons_received` | int | Bot summons count |

### Feature Engineering Module

**File**: `redditrepostsleuth/core/ml/feature_engineering.py`

```python
"""
Feature Engineering for Spam Detection ML Model

Handles feature preprocessing, scaling, and encoding.
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, RobustScaler

log = logging.getLogger(__name__)


@dataclass
class FeatureConfig:
    """Configuration for feature engineering."""

    # Features to use (in order)
    NUMERIC_FEATURES = [
        'repost_ratio',
        'adult_platform_ratio',
        'posts_per_day_avg',
        'karma_farming_sub_posts',
        'unique_subreddits_posted',
        'nsfw_post_ratio',
        'short_link_ratio',
        'total_posts_indexed',
        'summons_received',
        # Tier 2 features (may be missing)
        'account_age_days',
        'total_karma',
        'post_karma',
        'comment_karma',
        'karma_per_day',
    ]

    BOOLEAN_FEATURES = [
        'username_suspicious_pattern',
        'has_verified_email',
        'is_gold',
        'has_custom_avatar',
        'account_suspended',
    ]

    # Features that require Tier 2 data (may be missing)
    TIER2_FEATURES = [
        'account_age_days',
        'total_karma',
        'post_karma',
        'comment_karma',
        'karma_per_day',
        'has_verified_email',
        'is_gold',
        'has_custom_avatar',
        'account_suspended',
    ]

    # Default values for missing features
    DEFAULTS = {
        'account_age_days': 365,  # Assume 1 year if unknown
        'total_karma': 1000,
        'post_karma': 500,
        'comment_karma': 500,
        'karma_per_day': 2.0,
        'has_verified_email': True,
        'is_gold': False,
        'has_custom_avatar': True,
        'account_suspended': False,
    }


class FeatureEngineer:
    """
    Handles feature preprocessing for ML model.

    Responsibilities:
    - Feature extraction from database records
    - Missing value handling
    - Scaling/normalization
    - Feature encoding
    """

    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self.scaler: Optional[RobustScaler] = None
        self._is_fitted = False

    def extract_features(self, features_record) -> Dict[str, any]:
        """
        Extract features from a UserSpamFeatures database record.

        Args:
            features_record: UserSpamFeatures model instance

        Returns:
            Dict of feature name to value
        """
        extracted = {}

        # Numeric features
        for feat in self.config.NUMERIC_FEATURES:
            value = getattr(features_record, feat, None)
            if value is None and feat in self.config.DEFAULTS:
                value = self.config.DEFAULTS[feat]
            extracted[feat] = value if value is not None else 0

        # Boolean features (convert to int)
        for feat in self.config.BOOLEAN_FEATURES:
            value = getattr(features_record, feat, None)
            if value is None and feat in self.config.DEFAULTS:
                value = self.config.DEFAULTS[feat]
            extracted[feat] = int(value) if value is not None else 0

        return extracted

    def prepare_dataframe(
        self,
        records: List,
        labels: Optional[List[str]] = None
    ) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
        """
        Prepare DataFrame from list of feature records.

        Args:
            records: List of UserSpamFeatures or dicts
            labels: Optional list of labels (SPAM/LEGITIMATE)

        Returns:
            Tuple of (features DataFrame, labels Series or None)
        """
        data = []
        for record in records:
            if isinstance(record, dict):
                data.append(record)
            else:
                data.append(self.extract_features(record))

        df = pd.DataFrame(data)

        # Ensure all expected columns exist
        all_features = self.config.NUMERIC_FEATURES + self.config.BOOLEAN_FEATURES
        for feat in all_features:
            if feat not in df.columns:
                default = self.config.DEFAULTS.get(feat, 0)
                df[feat] = default

        # Reorder columns
        df = df[all_features]

        # Handle labels
        y = None
        if labels:
            y = pd.Series([1 if l == 'SPAM' else 0 for l in labels])

        return df, y

    def fit_scaler(self, X: pd.DataFrame) -> None:
        """
        Fit the scaler on training data.

        Uses RobustScaler to handle outliers in features like karma.
        """
        # Only scale numeric features (not booleans)
        numeric_cols = self.config.NUMERIC_FEATURES

        self.scaler = RobustScaler()
        self.scaler.fit(X[numeric_cols])
        self._is_fitted = True

        log.info(f"Fitted scaler on {len(numeric_cols)} numeric features")

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        """
        Transform features for model input.

        Args:
            X: DataFrame with features

        Returns:
            Numpy array ready for model
        """
        if not self._is_fitted:
            raise ValueError("Scaler not fitted. Call fit_scaler first.")

        X_copy = X.copy()

        # Scale numeric features
        numeric_cols = self.config.NUMERIC_FEATURES
        X_copy[numeric_cols] = self.scaler.transform(X_copy[numeric_cols])

        return X_copy.values

    def fit_transform(self, X: pd.DataFrame) -> np.ndarray:
        """Fit scaler and transform in one step."""
        self.fit_scaler(X)
        return self.transform(X)

    def get_feature_names(self) -> List[str]:
        """Get ordered list of feature names."""
        return self.config.NUMERIC_FEATURES + self.config.BOOLEAN_FEATURES


class FeatureImportanceAnalyzer:
    """Analyzes and reports feature importance."""

    @staticmethod
    def get_importance_report(
        model,
        feature_names: List[str]
    ) -> List[Tuple[str, float]]:
        """
        Get feature importance from trained model.

        Returns list of (feature_name, importance) sorted by importance.
        """
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
        elif hasattr(model, 'coef_'):
            importances = np.abs(model.coef_[0])
        else:
            return []

        importance_pairs = list(zip(feature_names, importances))
        return sorted(importance_pairs, key=lambda x: x[1], reverse=True)

    @staticmethod
    def print_importance_report(
        importance_pairs: List[Tuple[str, float]],
        top_n: int = 15
    ) -> str:
        """Format importance report as string."""
        lines = ["Feature Importance Report", "=" * 40]

        for i, (name, importance) in enumerate(importance_pairs[:top_n]):
            bar = "█" * int(importance * 50)
            lines.append(f"{i+1:2}. {name:30} {importance:.4f} {bar}")

        return "\n".join(lines)
```

---

## 3. Model Selection

### Recommended Model: Random Forest

**Rationale**:
- Handles mixed feature types (numeric + boolean)
- Robust to outliers
- Provides feature importance
- No strict assumptions about data distribution
- Good performance on tabular data

### Alternative Models to Compare

| Model | Pros | Cons |
|-------|------|------|
| **Random Forest** | Robust, interpretable | Can overfit with many trees |
| **Gradient Boosting** | Often better accuracy | Slower, less interpretable |
| **Logistic Regression** | Fast, interpretable | Assumes linear relationships |
| **XGBoost** | Best accuracy often | Requires tuning, complex |

### Ensemble Strategy

Use voting ensemble of multiple models for robustness:

```python
from sklearn.ensemble import VotingClassifier

ensemble = VotingClassifier(
    estimators=[
        ('rf', RandomForestClassifier()),
        ('gb', GradientBoostingClassifier()),
        ('lr', LogisticRegression()),
    ],
    voting='soft',  # Use probabilities
    weights=[2, 2, 1],  # Weight RF and GB higher
)
```

---

## 4. Training Pipeline

### File: `redditrepostsleuth/core/ml/spam_model_trainer.py`

```python
"""
Spam Detection Model Training Pipeline

Handles data loading, model training, evaluation, and serialization.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    GridSearchCV,
    StratifiedKFold,
    cross_val_score,
    train_test_split,
)
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.ml.feature_engineering import (
    FeatureEngineer,
    FeatureImportanceAnalyzer,
)

log = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for model training."""
    test_size: float = 0.2
    random_state: int = 42
    cv_folds: int = 5
    model_dir: str = 'models'


@dataclass
class TrainingResult:
    """Results from model training."""
    model_path: str
    scaler_path: str
    metadata_path: str
    metrics: Dict[str, float]
    feature_importance: List[Tuple[str, float]]
    training_timestamp: str
    training_samples: int
    test_samples: int


class SpamModelTrainer:
    """
    ML Model Training Pipeline for Spam Detection.

    Workflow:
    1. Load labeled data from database
    2. Engineer features
    3. Split train/test
    4. Train model(s)
    5. Evaluate and select best
    6. Save model and metadata
    """

    def __init__(
        self,
        uowm: UnitOfWorkManager,
        config: Optional[TrainingConfig] = None,
    ):
        self.uowm = uowm
        self.config = config or TrainingConfig()
        self.feature_engineer = FeatureEngineer()

    def load_training_data(self) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Load labeled training data from database.

        Returns:
            Tuple of (features DataFrame, labels Series)
        """
        log.info("Loading training data from database")

        with self.uowm.start() as uow:
            # Get all labels
            labels = uow.spam_training_labels.get_all()

            # Build dataset
            feature_records = []
            label_values = []

            for label in labels:
                # Get features for this user
                features = uow.spam_features.get_latest_by_username(label.username)

                if features:
                    feature_records.append(features)
                    label_values.append(label.label)
                else:
                    log.debug(f"No features found for labeled user: {label.username}")

        log.info(f"Loaded {len(feature_records)} samples with features")

        # Prepare DataFrame
        X, y = self.feature_engineer.prepare_dataframe(feature_records, label_values)

        return X, y

    def train_random_forest(
        self,
        X_train: np.ndarray,
        y_train: pd.Series,
    ) -> RandomForestClassifier:
        """Train Random Forest with hyperparameter tuning."""
        log.info("Training Random Forest model")

        param_grid = {
            'n_estimators': [100, 200],
            'max_depth': [10, 15, 20, None],
            'min_samples_split': [2, 5],
            'min_samples_leaf': [1, 2],
            'class_weight': ['balanced'],
        }

        rf = RandomForestClassifier(random_state=self.config.random_state)

        # Grid search with cross-validation
        grid_search = GridSearchCV(
            rf,
            param_grid,
            cv=self.config.cv_folds,
            scoring='roc_auc',
            n_jobs=-1,
            verbose=1,
        )

        grid_search.fit(X_train, y_train)

        log.info(f"Best RF params: {grid_search.best_params_}")
        log.info(f"Best RF CV score: {grid_search.best_score_:.4f}")

        return grid_search.best_estimator_

    def train_gradient_boosting(
        self,
        X_train: np.ndarray,
        y_train: pd.Series,
    ) -> GradientBoostingClassifier:
        """Train Gradient Boosting model."""
        log.info("Training Gradient Boosting model")

        gb = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=self.config.random_state,
        )

        gb.fit(X_train, y_train)

        return gb

    def train_ensemble(
        self,
        X_train: np.ndarray,
        y_train: pd.Series,
    ) -> VotingClassifier:
        """Train ensemble of models."""
        log.info("Training ensemble model")

        rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            class_weight='balanced',
            random_state=self.config.random_state,
        )

        gb = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=self.config.random_state,
        )

        lr = LogisticRegression(
            class_weight='balanced',
            max_iter=1000,
            random_state=self.config.random_state,
        )

        ensemble = VotingClassifier(
            estimators=[
                ('rf', rf),
                ('gb', gb),
                ('lr', lr),
            ],
            voting='soft',
            weights=[2, 2, 1],
        )

        ensemble.fit(X_train, y_train)

        return ensemble

    def evaluate_model(
        self,
        model,
        X_test: np.ndarray,
        y_test: pd.Series,
    ) -> Dict[str, float]:
        """
        Evaluate model on test set.

        Returns dict of metrics.
        """
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred),
            'recall': recall_score(y_test, y_pred),
            'f1': f1_score(y_test, y_pred),
            'roc_auc': roc_auc_score(y_test, y_prob),
        }

        # Log detailed report
        log.info("\nClassification Report:")
        log.info(classification_report(y_test, y_pred, target_names=['LEGITIMATE', 'SPAM']))

        log.info("\nConfusion Matrix:")
        log.info(confusion_matrix(y_test, y_pred))

        return metrics

    def train_and_save(self, model_version: str = 'v1') -> TrainingResult:
        """
        Full training pipeline: load, train, evaluate, save.

        Args:
            model_version: Version string for model files

        Returns:
            TrainingResult with paths and metrics
        """
        log.info(f"Starting training pipeline for version: {model_version}")

        # 1. Load data
        X, y = self.load_training_data()

        log.info(f"Dataset: {len(X)} samples, {y.sum()} SPAM, {len(y) - y.sum()} LEGITIMATE")

        # 2. Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=self.config.test_size,
            random_state=self.config.random_state,
            stratify=y,
        )

        # 3. Scale features
        X_train_scaled = self.feature_engineer.fit_transform(X_train)
        X_test_scaled = self.feature_engineer.transform(X_test)

        # 4. Train model (use ensemble for production)
        model = self.train_ensemble(X_train_scaled, y_train)

        # 5. Evaluate
        metrics = self.evaluate_model(model, X_test_scaled, y_test)

        log.info(f"Final Metrics: {metrics}")

        # 6. Get feature importance (from RF component)
        rf_model = model.named_estimators_['rf']
        feature_names = self.feature_engineer.get_feature_names()
        importance = FeatureImportanceAnalyzer.get_importance_report(rf_model, feature_names)

        log.info("\n" + FeatureImportanceAnalyzer.print_importance_report(importance))

        # 7. Save model
        model_dir = Path(self.config.model_dir)
        model_dir.mkdir(exist_ok=True)

        model_path = model_dir / f'spam_detector_{model_version}.pkl'
        scaler_path = model_dir / f'feature_scaler_{model_version}.pkl'
        metadata_path = model_dir / f'spam_detector_{model_version}_metadata.json'

        joblib.dump(model, model_path)
        joblib.dump(self.feature_engineer.scaler, scaler_path)

        metadata = {
            'version': model_version,
            'trained_at': datetime.utcnow().isoformat(),
            'training_samples': len(X_train),
            'test_samples': len(X_test),
            'metrics': metrics,
            'feature_names': feature_names,
            'feature_importance': importance[:10],  # Top 10
            'class_distribution': {
                'spam': int(y_train.sum()),
                'legitimate': int(len(y_train) - y_train.sum()),
            },
        }

        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        log.info(f"Model saved to: {model_path}")
        log.info(f"Scaler saved to: {scaler_path}")
        log.info(f"Metadata saved to: {metadata_path}")

        return TrainingResult(
            model_path=str(model_path),
            scaler_path=str(scaler_path),
            metadata_path=str(metadata_path),
            metrics=metrics,
            feature_importance=importance,
            training_timestamp=metadata['trained_at'],
            training_samples=len(X_train),
            test_samples=len(X_test),
        )

    def cross_validate(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
        """
        Perform cross-validation to estimate model performance.

        Returns dict of mean CV scores.
        """
        X_scaled = self.feature_engineer.fit_transform(X)

        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            class_weight='balanced',
            random_state=self.config.random_state,
        )

        cv = StratifiedKFold(n_splits=self.config.cv_folds, shuffle=True, random_state=self.config.random_state)

        scores = {
            'accuracy': cross_val_score(model, X_scaled, y, cv=cv, scoring='accuracy'),
            'precision': cross_val_score(model, X_scaled, y, cv=cv, scoring='precision'),
            'recall': cross_val_score(model, X_scaled, y, cv=cv, scoring='recall'),
            'f1': cross_val_score(model, X_scaled, y, cv=cv, scoring='f1'),
            'roc_auc': cross_val_score(model, X_scaled, y, cv=cv, scoring='roc_auc'),
        }

        return {
            metric: {
                'mean': float(scores[metric].mean()),
                'std': float(scores[metric].std()),
            }
            for metric in scores
        }
```

---

## 5. Model Evaluation

### Evaluation Metrics

| Metric | Target | Interpretation |
|--------|--------|----------------|
| **AUC-ROC** | ≥0.85 | Overall discrimination ability |
| **Precision** | ≥0.80 | % of flagged users that are actually spam |
| **Recall** | ≥0.75 | % of actual spam caught |
| **F1 Score** | ≥0.77 | Balance of precision/recall |
| **False Positive Rate** | ≤5% | Critical - don't flag legitimate users |

### Evaluation Module

**File**: `redditrepostsleuth/core/ml/model_evaluator.py`

```python
"""
Model Evaluation Module

Provides comprehensive evaluation and comparison of models.
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_curve,
)

log = logging.getLogger(__name__)


class ModelEvaluator:
    """Comprehensive model evaluation."""

    def __init__(self, model, X_test: np.ndarray, y_test: pd.Series):
        self.model = model
        self.X_test = X_test
        self.y_test = y_test

        self.y_pred = model.predict(X_test)
        self.y_prob = model.predict_proba(X_test)[:, 1]

    def get_confusion_matrix(self) -> np.ndarray:
        """Get confusion matrix."""
        return confusion_matrix(self.y_test, self.y_pred)

    def get_classification_report(self) -> str:
        """Get detailed classification report."""
        return classification_report(
            self.y_test,
            self.y_pred,
            target_names=['LEGITIMATE', 'SPAM']
        )

    def get_threshold_analysis(
        self,
        thresholds: Optional[List[float]] = None
    ) -> pd.DataFrame:
        """
        Analyze metrics at different probability thresholds.

        Useful for finding optimal threshold for production.
        """
        if thresholds is None:
            thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

        results = []
        for threshold in thresholds:
            y_pred_t = (self.y_prob >= threshold).astype(int)

            tn, fp, fn, tp = confusion_matrix(self.y_test, y_pred_t).ravel()

            results.append({
                'threshold': threshold,
                'precision': tp / (tp + fp) if (tp + fp) > 0 else 0,
                'recall': tp / (tp + fn) if (tp + fn) > 0 else 0,
                'fpr': fp / (fp + tn) if (fp + tn) > 0 else 0,  # False positive rate
                'flagged_count': int(y_pred_t.sum()),
                'flagged_pct': y_pred_t.sum() / len(y_pred_t),
            })

        return pd.DataFrame(results)

    def get_roc_curve(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get ROC curve data."""
        return roc_curve(self.y_test, self.y_prob)

    def get_precision_recall_curve(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get precision-recall curve data."""
        return precision_recall_curve(self.y_test, self.y_prob)

    def get_calibration_curve(self, n_bins: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get calibration curve (reliability diagram).

        Shows if predicted probabilities match actual frequencies.
        """
        prob_true, prob_pred = calibration_curve(
            self.y_test,
            self.y_prob,
            n_bins=n_bins,
            strategy='uniform'
        )
        return prob_true, prob_pred

    def find_optimal_threshold(
        self,
        max_fpr: float = 0.05,
    ) -> Dict[str, float]:
        """
        Find optimal threshold with constraint on false positive rate.

        Args:
            max_fpr: Maximum acceptable false positive rate

        Returns:
            Dict with optimal threshold and metrics at that threshold
        """
        df = self.get_threshold_analysis(
            thresholds=np.arange(0.1, 1.0, 0.05).tolist()
        )

        # Filter to acceptable FPR
        acceptable = df[df['fpr'] <= max_fpr]

        if acceptable.empty:
            # If no threshold meets constraint, use highest available
            acceptable = df.nlargest(1, 'threshold')

        # Choose threshold with best F1 among acceptable
        acceptable['f1'] = (
            2 * acceptable['precision'] * acceptable['recall'] /
            (acceptable['precision'] + acceptable['recall'])
        )
        best = acceptable.loc[acceptable['f1'].idxmax()]

        return {
            'optimal_threshold': float(best['threshold']),
            'precision': float(best['precision']),
            'recall': float(best['recall']),
            'fpr': float(best['fpr']),
            'f1': float(best['f1']),
        }
```

---

## 6. Model Deployment

### Model Storage

Models are stored in the `models/` directory (gitignored) with versioning:

```
models/
├── spam_detector_v1.pkl           # Model file
├── spam_detector_v1_metadata.json # Metadata
├── feature_scaler_v1.pkl          # Feature scaler
├── spam_detector_v2.pkl           # Newer version
├── spam_detector_v2_metadata.json
└── feature_scaler_v2.pkl
```

### Deployment Configuration

**File**: `redditrepostsleuth/core/config/ml_config.py`

```python
"""ML Model Configuration."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MLConfig:
    """Configuration for ML model deployment."""
    model_dir: Path = Path('models')
    active_model_version: str = 'v1'
    prediction_threshold: float = 0.7  # Default threshold
    enable_ml_scoring: bool = False  # Feature flag

    @property
    def model_path(self) -> Path:
        return self.model_dir / f'spam_detector_{self.active_model_version}.pkl'

    @property
    def scaler_path(self) -> Path:
        return self.model_dir / f'feature_scaler_{self.active_model_version}.pkl'

    @property
    def metadata_path(self) -> Path:
        return self.model_dir / f'spam_detector_{self.active_model_version}_metadata.json'
```

### Deployment Checklist

- [ ] Model file exists at configured path
- [ ] Scaler file exists at configured path
- [ ] Metadata file exists with metrics
- [ ] AUC-ROC ≥ 0.85 in metadata
- [ ] FPR ≤ 0.05 at chosen threshold
- [ ] Feature names match current code
- [ ] Tested on recent data

---

## 6.5. Model Loading Optimization

Production inference requires fast model loading. Implement lazy loading and caching strategies:

### Lazy Loading Strategy

**File**: `redditrepostsleuth/core/ml/model_cache.py`

```python
"""
Model caching and lazy loading for production.

Models are large (~50MB+). Lazy loading defers loading until first use.
Caching keeps models in memory to avoid repeated disk/network I/O.
"""
import logging
from pathlib import Path
from typing import Optional

import joblib

log = logging.getLogger(__name__)


class ModelCache:
    """
    Thread-safe model caching with lazy loading.

    Features:
    - Load model only when first needed
    - Keep in memory for subsequent requests
    - Version support for model updates
    """

    def __init__(self, model_dir: str):
        self.model_dir = Path(model_dir)
        self._model_cache = {}
        self._scaler_cache = {}

    def get_model(self, version: str = 'v1'):
        """
        Get model, loading if necessary.

        Args:
            version: Model version (e.g., 'v1', 'v2')

        Returns:
            Loaded model
        """
        cache_key = f"model_{version}"

        if cache_key not in self._model_cache:
            log.info(f"Loading model version {version} (first use)")
            model_path = self.model_dir / f'spam_detector_{version}.pkl'

            if not model_path.exists():
                raise FileNotFoundError(f"Model not found: {model_path}")

            self._model_cache[cache_key] = joblib.load(model_path)

        return self._model_cache[cache_key]

    def get_scaler(self, version: str = 'v1'):
        """Get feature scaler, loading if necessary."""
        cache_key = f"scaler_{version}"

        if cache_key not in self._scaler_cache:
            log.info(f"Loading scaler version {version}")
            scaler_path = self.model_dir / f'feature_scaler_{version}.pkl'

            if not scaler_path.exists():
                raise FileNotFoundError(f"Scaler not found: {scaler_path}")

            self._scaler_cache[cache_key] = joblib.load(scaler_path)

        return self._scaler_cache[cache_key]

    def preload(self, version: str = 'v1') -> None:
        """
        Eagerly load model and scaler (for startup).

        Call this on application startup to avoid cold start.
        """
        log.info(f"Preloading model and scaler version {version}")
        _ = self.get_model(version)
        _ = self.get_scaler(version)

    def invalidate(self, version: Optional[str] = None) -> None:
        """
        Invalidate cached model(s).

        Use when deploying new model version.

        Args:
            version: Specific version to invalidate, or None for all
        """
        if version:
            self._model_cache.pop(f"model_{version}", None)
            self._scaler_cache.pop(f"scaler_{version}", None)
            log.info(f"Invalidated cache for version {version}")
        else:
            self._model_cache.clear()
            self._scaler_cache.clear()
            log.info("Invalidated all cached models")

    def get_memory_usage(self) -> dict:
        """Get approximate memory usage of cached models."""
        import sys
        return {
            'model_count': len(self._model_cache),
            'scaler_count': len(self._scaler_cache),
            'model_memory_mb': sum(
                sys.getsizeof(m) for m in self._model_cache.values()
            ) / 1024 / 1024,
        }
```

### Integration with Predictor

```python
class SpamModelPredictor:
    # Global cache (singleton pattern)
    _cache: Optional[ModelCache] = None

    @classmethod
    def initialize_cache(cls, model_dir: str):
        """Initialize global model cache (call on app startup)."""
        cls._cache = ModelCache(model_dir)
        cls._cache.preload()  # Eager load
        log.info("Model cache initialized and preloaded")

    def __init__(self, model_version: str = 'v1'):
        self.model_version = model_version
        # Use global cache
        if self._cache is None:
            raise RuntimeError("ModelCache not initialized")

    def predict(self, features: dict) -> float:
        """Predict spam score for features."""
        model = self._cache.get_model(self.model_version)
        scaler = self._cache.get_scaler(self.model_version)

        # Fast prediction from cache
        X_scaled = scaler.transform([features])
        return model.predict_proba(X_scaled)[0, 1]
```

### Application Startup

```python
# In main application initialization
from redditrepostsleuth.core.ml.spam_model_predictor import SpamModelPredictor

# Initialize model cache on startup (one-time)
SpamModelPredictor.initialize_cache(model_dir='/models')

# Now predictors will use cached models
predictor = SpamModelPredictor(model_version='v1')
```

### Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| First prediction (cold start) | 500-1000ms | Includes model load |
| Subsequent predictions (cached) | 10-50ms | From memory |
| Preload on startup | 2-5 seconds | One-time, happens on app start |

### Memory Management

Monitor and optimize memory usage:

```python
cache = SpamModelPredictor._cache
usage = cache.get_memory_usage()
print(f"Models in memory: {usage['model_count']}")
print(f"Memory usage: {usage['model_memory_mb']:.1f} MB")
```

For multi-version deployments, limit cached versions:

```python
# Only keep current and previous version
for old_version in ['v1', 'v2']:  # Clean up old versions
    cache.invalidate(old_version)

cache.preload('v4')  # Load new version
```

---

## 7. Inference Service

### File: `redditrepostsleuth/core/ml/spam_model_predictor.py`

```python
"""
Spam Model Inference Service

Loads trained model and provides predictions.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np

from redditrepostsleuth.core.db.databasemodels import UserSpamFeatures
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.ml.feature_engineering import FeatureEngineer

log = logging.getLogger(__name__)


class SpamModelPredictor:
    """
    ML Model Inference for Spam Detection.

    Provides predictions using trained model.
    Thread-safe for use in async/celery tasks.
    """

    def __init__(
        self,
        model_path: str,
        scaler_path: str,
        uowm: UnitOfWorkManager,
        threshold: float = 0.7,
    ):
        """
        Initialize predictor with model files.

        Args:
            model_path: Path to trained model pickle
            scaler_path: Path to feature scaler pickle
            uowm: Unit of Work Manager
            threshold: Probability threshold for positive classification
        """
        self.uowm = uowm
        self.threshold = threshold

        # Load model and scaler
        log.info(f"Loading model from: {model_path}")
        self.model = joblib.load(model_path)

        log.info(f"Loading scaler from: {scaler_path}")
        self.scaler = joblib.load(scaler_path)

        # Initialize feature engineer with loaded scaler
        self.feature_engineer = FeatureEngineer()
        self.feature_engineer.scaler = self.scaler
        self.feature_engineer._is_fitted = True

        log.info("Model predictor initialized")

    def predict_from_features(
        self,
        features: UserSpamFeatures
    ) -> Dict[str, any]:
        """
        Predict spam probability from feature record.

        Args:
            features: UserSpamFeatures database record

        Returns:
            Dict with prediction, probability, and reasons
        """
        # Extract and prepare features
        feature_dict = self.feature_engineer.extract_features(features)
        X, _ = self.feature_engineer.prepare_dataframe([feature_dict])
        X_scaled = self.feature_engineer.transform(X)

        # Get prediction
        prob = self.model.predict_proba(X_scaled)[0, 1]
        is_spam = prob >= self.threshold

        return {
            'username': features.username,
            'ml_probability': float(prob),
            'ml_prediction': 'SPAM' if is_spam else 'LEGITIMATE',
            'threshold_used': self.threshold,
            'model_version': getattr(self, 'model_version', 'unknown'),
        }

    def predict_for_user(self, username: str) -> Optional[Dict[str, any]]:
        """
        Predict spam probability for a user by username.

        Fetches latest features from database.
        """
        with self.uowm.start() as uow:
            features = uow.spam_features.get_latest_by_username(username)

        if not features:
            log.warning(f"No features found for user: {username}")
            return None

        return self.predict_from_features(features)

    def batch_predict(
        self,
        usernames: List[str]
    ) -> Dict[str, Dict[str, any]]:
        """
        Predict for multiple users.

        Returns dict mapping username to prediction result.
        """
        results = {}

        with self.uowm.start() as uow:
            for username in usernames:
                features = uow.spam_features.get_latest_by_username(username)
                if features:
                    results[username] = self.predict_from_features(features)
                else:
                    results[username] = None

        return results

    def get_model_info(self) -> Dict[str, any]:
        """Get information about loaded model."""
        info = {
            'threshold': self.threshold,
            'feature_count': len(self.feature_engineer.get_feature_names()),
            'feature_names': self.feature_engineer.get_feature_names(),
        }

        # Try to get model type
        model_type = type(self.model).__name__
        info['model_type'] = model_type

        return info


class MLScorerIntegration:
    """
    Integration layer for ML scoring in the spam detection pipeline.

    Combines rule-based and ML scores.
    """

    def __init__(
        self,
        predictor: SpamModelPredictor,
        rule_weight: float = 0.4,
        ml_weight: float = 0.6,
    ):
        """
        Initialize integration layer.

        Args:
            predictor: ML model predictor
            rule_weight: Weight for rule-based score
            ml_weight: Weight for ML score
        """
        self.predictor = predictor
        self.rule_weight = rule_weight
        self.ml_weight = ml_weight

    def get_combined_score(
        self,
        username: str,
        rule_score: float,
    ) -> Dict[str, any]:
        """
        Get combined rule-based and ML score.

        Args:
            username: Reddit username
            rule_score: Score from rule-based system

        Returns:
            Dict with combined score and components
        """
        ml_result = self.predictor.predict_for_user(username)

        if ml_result is None:
            # No ML prediction available, use rule-based only
            return {
                'final_score': rule_score,
                'rule_score': rule_score,
                'ml_score': None,
                'ml_available': False,
            }

        ml_score = ml_result['ml_probability']

        # Weighted combination
        combined = (self.rule_weight * rule_score) + (self.ml_weight * ml_score)

        return {
            'final_score': float(combined),
            'rule_score': rule_score,
            'ml_score': ml_score,
            'ml_prediction': ml_result['ml_prediction'],
            'ml_available': True,
        }
```

---

## 8. Monitoring & Retraining

### Performance Monitoring

Track model performance over time:

```python
class ModelMonitor:
    """Monitors model performance in production."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def log_prediction(
        self,
        username: str,
        ml_score: float,
        prediction: str,
        actual_outcome: Optional[str] = None,
    ) -> None:
        """Log a prediction for later analysis."""
        # Store in database for monitoring
        pass

    def calculate_drift_metrics(self, days: int = 30) -> Dict[str, float]:
        """
        Calculate feature drift metrics.

        Compares recent feature distributions to training data.
        """
        pass

    def get_performance_over_time(self, days: int = 30) -> Dict[str, any]:
        """
        Get performance metrics over time.

        Requires ground truth (verified labels) to calculate.
        """
        pass
```

### Retraining Triggers

Trigger model retraining when:

1. **Data drift**: Feature distributions shift significantly
2. **Performance degradation**: Verified FPR exceeds 10%
3. **New labeled data**: 200+ new labels added
4. **Time-based**: Every 90 days regardless

### Retraining Pipeline

```python
@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def retrain_model(self, version: str) -> dict:
    """
    Retrain the spam detection model.

    Should be run manually or on schedule.
    """
    from redditrepostsleuth.core.ml.spam_model_trainer import SpamModelTrainer

    trainer = SpamModelTrainer(self.uowm)
    result = trainer.train_and_save(model_version=version)

    return {
        'model_path': result.model_path,
        'metrics': result.metrics,
        'timestamp': result.training_timestamp,
    }
```

---

## 9. Testing Strategy

### Unit Tests

```python
"""Tests for ML components."""
import unittest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock

from redditrepostsleuth.core.ml.feature_engineering import (
    FeatureEngineer,
    FeatureConfig,
)


class TestFeatureEngineer(unittest.TestCase):

    def setUp(self):
        self.engineer = FeatureEngineer()

    def test_extract_features_from_record(self):
        """Test feature extraction from database record."""
        mock_record = MagicMock()
        mock_record.repost_ratio = 0.5
        mock_record.adult_platform_ratio = 0.1
        mock_record.posts_per_day_avg = 5.0
        mock_record.account_age_days = 100
        mock_record.username_suspicious_pattern = True

        features = self.engineer.extract_features(mock_record)

        self.assertEqual(features['repost_ratio'], 0.5)
        self.assertEqual(features['username_suspicious_pattern'], 1)

    def test_prepare_dataframe_shape(self):
        """Test DataFrame preparation."""
        records = [
            {'repost_ratio': 0.5, 'adult_platform_ratio': 0.1},
            {'repost_ratio': 0.8, 'adult_platform_ratio': 0.5},
        ]
        labels = ['LEGITIMATE', 'SPAM']

        X, y = self.engineer.prepare_dataframe(records, labels)

        self.assertEqual(len(X), 2)
        self.assertEqual(y.tolist(), [0, 1])

    def test_scaling(self):
        """Test feature scaling."""
        X = pd.DataFrame({
            'repost_ratio': [0.1, 0.5, 0.9],
            'posts_per_day_avg': [1, 10, 100],
            'username_suspicious_pattern': [0, 1, 0],
        })

        # Add missing columns with defaults
        for col in self.engineer.config.NUMERIC_FEATURES:
            if col not in X.columns:
                X[col] = 0
        for col in self.engineer.config.BOOLEAN_FEATURES:
            if col not in X.columns:
                X[col] = 0

        X_scaled = self.engineer.fit_transform(X)

        # Scaled numeric features should have reasonable range
        self.assertTrue(np.abs(X_scaled[:, 0]).max() < 10)
```

### Integration Tests

```python
"""Integration tests for ML pipeline."""
import unittest


class TestMLPipelineIntegration(unittest.TestCase):
    """Test full ML training pipeline."""

    @unittest.skip("Requires database with training data")
    def test_full_training_pipeline(self):
        """Test complete training flow."""
        pass

    @unittest.skip("Requires trained model")
    def test_inference_pipeline(self):
        """Test prediction flow."""
        pass
```

---

## 10. Verification Checklist

### Pre-Training
- [ ] ≥500 SPAM labels in database
- [ ] ≥500 LEGITIMATE labels in database
- [ ] Features computed for ≥90% of labeled users
- [ ] Dependencies installed (scikit-learn, pandas, etc.)

### Training
- [ ] Model training completes without errors
- [ ] AUC-ROC ≥ 0.85 on test set
- [ ] Precision ≥ 0.80 at chosen threshold
- [ ] FPR ≤ 0.05 at chosen threshold
- [ ] Model files saved correctly

### Deployment
- [ ] Model loads without errors
- [ ] Predictor produces valid probabilities (0-1)
- [ ] Integration with scoring system works
- [ ] Feature flag enables/disables ML scoring

### Monitoring
- [ ] Predictions logged for analysis
- [ ] Drift detection implemented
- [ ] Retraining pipeline tested

---

## Dependencies

### Python Packages (New)

```txt
scikit-learn>=1.3.0
pandas>=2.0.0
numpy>=1.24.0
joblib>=1.3.0
imbalanced-learn>=0.11.0
```

### Infrastructure
- Sufficient RAM for model loading (~500MB)
- Disk space for model files (~100MB)

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| Feature engineering module | 4 hours |
| Training pipeline | 6 hours |
| Model evaluation | 3 hours |
| Inference service | 4 hours |
| Integration with scoring | 3 hours |
| Monitoring setup | 3 hours |
| Testing | 4 hours |
| Documentation | 2 hours |
| **Total** | ~29 hours |
