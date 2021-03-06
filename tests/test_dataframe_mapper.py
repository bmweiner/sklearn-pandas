import pytest

# In py3, mock is included with the unittest standard library
# In py2, it's a separate package
try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock

from pandas import DataFrame
import pandas as pd
from scipy import sparse
from sklearn.datasets import load_iris
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import Imputer, StandardScaler
from sklearn.base import BaseEstimator, TransformerMixin
import numpy as np
from numpy.testing import assert_array_equal
import pickle

from sklearn_pandas import DataFrameMapper, cross_val_score
from sklearn_pandas.dataframe_mapper import _handle_feature, _build_transformer
from sklearn_pandas.pipeline import TransformerPipeline


class MockXTransformer(object):
    """
    Mock transformer that accepts no y argument.
    """
    def fit(self, X):
        return self

    def transform(self, X):
        return X


class MockTClassifier(object):
    """
    Mock transformer/classifier.
    """
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return X

    def predict(self, X):
        return True


class ToSparseTransformer(BaseEstimator, TransformerMixin):
    """
    Transforms numpy matrix to sparse format.
    """
    def fit(self, X):
        return self

    def transform(self, X):
        return sparse.csr_matrix(X)


@pytest.fixture
def simple_dataframe():
    return pd.DataFrame({'a': [1, 2, 3]})


def test_nonexistent_columns_explicit_fail(simple_dataframe):
    """
    If a nonexistent column is selected, KeyError is raised.
    """
    mapper = DataFrameMapper(None)
    with pytest.raises(KeyError):
        mapper._get_col_subset(simple_dataframe, ['nonexistent_feature'])


def test_get_col_subset_single_column_array(simple_dataframe):
    """
    Selecting a single column should return a 1-dimensional numpy array.
    """
    mapper = DataFrameMapper(None)
    array = mapper._get_col_subset(simple_dataframe, "a")

    assert type(array) == np.ndarray
    assert array.shape == (len(simple_dataframe["a"]),)


def test_get_col_subset_single_column_list(simple_dataframe):
    """
    Selecting a list of columns (even if the list contains a single element)
    should return a 2-dimensional numpy array.
    """
    mapper = DataFrameMapper(None)
    array = mapper._get_col_subset(simple_dataframe, ["a"])

    assert type(array) == np.ndarray
    assert array.shape == (len(simple_dataframe["a"]), 1)


def test_cols_string_array(simple_dataframe):
    """
    If an string specified as the columns, the transformer
    is called with a 1-d array as input.
    """
    df = simple_dataframe
    mock_transformer = Mock()
    mock_transformer.transform.return_value = np.array([1, 2, 3])  # do nothing
    mapper = DataFrameMapper([("a", mock_transformer)])

    mapper.fit_transform(df)
    args, kwargs = mock_transformer.fit.call_args
    assert args[0].shape == (3,)


def test_cols_list_column_vector(simple_dataframe):
    """
    If a one-element list is specified as the columns, the transformer
    is called with a column vector as input.
    """
    df = simple_dataframe
    mock_transformer = Mock()
    mock_transformer.transform.return_value = np.array([1, 2, 3])  # do nothing
    mapper = DataFrameMapper([(["a"], mock_transformer)])

    mapper.fit_transform(df)
    args, kwargs = mock_transformer.fit.call_args
    assert args[0].shape == (3, 1)


def test_handle_feature_2dim():
    """
    2-dimensional arrays are returned unchanged.
    """
    array = np.array([[1, 2], [3, 4]])
    assert_array_equal(_handle_feature(array), array)


def test_handle_feature_1dim():
    """
    1-dimensional arrays are converted to 2-dimensional column vectors.
    """
    array = np.array([1, 2])
    assert_array_equal(_handle_feature(array), np.array([[1], [2]]))


def test_build_transformers():
    """
    When a list of transformers is passed, return a pipeline with
    each element of the iterable as a step of the pipeline.
    """
    transformers = [MockTClassifier(), MockTClassifier()]
    pipeline = _build_transformer(transformers)
    assert isinstance(pipeline, Pipeline)
    for ix, transformer in enumerate(transformers):
        assert pipeline.steps[ix][1] == transformer


def test_list_transformers_single_arg(simple_dataframe):
    """
    Multiple transformers can be specified in a list even if some of them
    only accept one X argument instead of two (X, y).
    """
    mapper = DataFrameMapper([
        ('a', [MockXTransformer()])
    ])
    # doesn't fail
    mapper.fit_transform(simple_dataframe)


def test_list_transformers():
    """
    Specifying a list of transformers applies them sequentially to the
    selected column.
    """
    dataframe = pd.DataFrame({"a": [1, np.nan, 3], "b": [1, 5, 7]})

    mapper = DataFrameMapper([
        (["a"], [Imputer(), StandardScaler()]),
        (["b"], StandardScaler()),
    ])
    dmatrix = mapper.fit_transform(dataframe)

    assert pd.isnull(dmatrix).sum() == 0  # no null values

    # all features have mean 0 and std deviation 1 (standardized)
    assert (abs(dmatrix.mean(axis=0) - 0) <= 1e-6).all()
    assert (abs(dmatrix.std(axis=0) - 1) <= 1e-6).all()


def test_list_transformers_old_unpickle(simple_dataframe):
    mapper = DataFrameMapper(None)
    # simulate the mapper was created with < 1.0.0 code
    mapper.features = [('a', [MockXTransformer()])]
    mapper_pickled = pickle.dumps(mapper)

    loaded_mapper = pickle.loads(mapper_pickled)
    transformer = loaded_mapper.features[0][1]
    assert isinstance(transformer, TransformerPipeline)
    assert isinstance(transformer.steps[0][1], MockXTransformer)


def test_sparse_features(simple_dataframe):
    """
    If any of the extracted features is sparse and "sparse" argument
    is true, the hstacked result is also sparse.
    """
    df = simple_dataframe
    mapper = DataFrameMapper([
        ("a", ToSparseTransformer())
    ], sparse=True)
    dmatrix = mapper.fit_transform(df)

    assert type(dmatrix) == sparse.csr.csr_matrix


def test_sparse_off(simple_dataframe):
    """
    If the resulting features are sparse but the "sparse" argument
    of the mapper is False, return a non-sparse matrix.
    """
    df = simple_dataframe
    mapper = DataFrameMapper([
        ("a", ToSparseTransformer())
    ], sparse=False)

    dmatrix = mapper.fit_transform(df)
    assert type(dmatrix) != sparse.csr.csr_matrix


# Integration tests with real dataframes

@pytest.fixture
def iris_dataframe():
    iris = load_iris()
    return DataFrame(
        data={
            iris.feature_names[0]: iris.data[:, 0],
            iris.feature_names[1]: iris.data[:, 1],
            iris.feature_names[2]: iris.data[:, 2],
            iris.feature_names[3]: iris.data[:, 3],
            "species": np.array([iris.target_names[e] for e in iris.target])
        }
    )


@pytest.fixture
def cars_dataframe():
    return pd.read_csv("tests/test_data/cars.csv.gz", compression='gzip')


def test_with_iris_dataframe(iris_dataframe):
    pipeline = Pipeline([
        ("preprocess", DataFrameMapper([
            ("petal length (cm)", None),
            ("petal width (cm)", None),
            ("sepal length (cm)", None),
            ("sepal width (cm)", None),
        ])),
        ("classify", SVC(kernel='linear'))
    ])
    data = iris_dataframe.drop("species", axis=1)
    labels = iris_dataframe["species"]
    scores = cross_val_score(pipeline, data, labels)
    assert scores.mean() > 0.96
    assert (scores.std() * 2) < 0.04


def test_with_car_dataframe(cars_dataframe):
    pipeline = Pipeline([
        ("preprocess", DataFrameMapper([
            ("description", CountVectorizer()),
        ])),
        ("classify", SVC(kernel='linear'))
    ])
    data = cars_dataframe.drop("model", axis=1)
    labels = cars_dataframe["model"]
    scores = cross_val_score(pipeline, data, labels)
    assert scores.mean() > 0.30
