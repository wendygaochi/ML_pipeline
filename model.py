from pathlib import Path
import argparse
import logging
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectKBest
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_cols_to_dummy():
    cols_to_dummy = ["basin", "region", "lga", "recorded_by",
                "extraction_type", "extraction_type_group",
                "extraction_type_class",
                "management", "management_group",
                "payment", "payment_type",
                "water_quality", "quality_group", "quantity", "quantity_group",
                "source", "source_type", "source_class",
                "waterpoint_type", "waterpoint_type_group"]
    return cols_to_dummy


def get_cols_to_drop():
    cols_to_drop = ["date_recorded", "funder", "installer", "wpt_name",
                    "subvillage", "ward", "public_meeting", "permit",
                    "scheme_name", "scheme_management"]
    return cols_to_drop


def feature_preprocessing(df, trained_transformers=None):
    """
    Drop and dummy training features

    Params
    ------
    df, pd.DataFrame
        contains the features for the model
    trained_transformers, dict of dicts of LabelEncoder + OneHotEncoder
        default = None

        bookkeeping for transformers that are used to dummy

        If trained_transformers=None, we are transforming the
        training data and want to store the LabelEncoder and
        OneHotEncoder for the dummied features so we can re-create
        them later on the test data.

        If trained_transformers has data in it, we are transforming
        the testing data and want to retrieve the already-fit
        transformers rather than creating new ones.

        trained_transformers format:
            tt['col_1'] = {"LabelEncoder":<LabelEncoder fit on col_1>,
                           "OneHotEncoder":<OneHotEncoder fit on col_1>}
            tt['col_2'] = {"LabelEncoder":<LabelEncoder fit on col_2>,
                           "OneHotEncoder":<OneHotEncoder fit on col_2>}


    Returns
    -------
    pd.DataFrame
        same dataframe that went in, but with
        columns dropped/dummied per the configurations
        in get_cols_to_dummy() and get_cols_to_drop()
    """
    cols_to_dummy = get_cols_to_dummy()
    cols_to_drop = get_cols_to_drop()
    df = df.drop(cols_to_drop, axis=1)
    logger.info("dropped columns")
    logger.info(cols_to_drop)

    # dummying!
    
    if trained_transformers is None:
        trained_transformers = {}

    for column_name in cols_to_dummy:
        column = np.array(df[column_name].tolist())

        # transformers exist already, use them
        if column_name in trained_transformers.keys():
            tt = trained_transformers[column_name]
            le = tt["LabelEncoder"]
            enc = tt["OneHotEncoder"]

            # add handling for new categories that might appear
            le.classes_ = np.append(le.classes_, np.array(["Other - new"]))
            logger.debug("eligible classes for transform: {}".format(le.classes_))
            logger.debug("classes in the dataset to be transformed: {}".format(set(column)))
            non_overlap = set([ii for ii in column if ii not in le.classes_])
            logger.debug("trouble columns: ")
            logger.debug(non_overlap)


            for ii in range(len(column)-1):
                if column[ii] in non_overlap:
                    logger.debug("changing column {} from {} to Other - new".format(ii, column[ii]))
                    column[ii] = "Other - new"

            int_column = le.transform(column).reshape(-1, 1)
            new_column = enc.transform(int_column).toarray()

        # transformers do not exist yet, create/store them
        else:
            le = LabelEncoder()
            int_column = le.fit_transform(column).reshape(-1, 1)
            enc = OneHotEncoder(handle_unknown="ignore")
            new_column = enc.fit_transform(int_column).toarray()
            tt = {"LabelEncoder":le, "OneHotEncoder":enc} 
            trained_transformers[column_name] = tt

        # once we've dummied, want to remove original col 
        df.drop(column_name, axis=1, inplace=True)
        logger.debug("dummying column {}".format(column_name))
        logger.debug("  values: {}".format(le.classes_))

        for ii in range(len(new_column[0])):
            this_column_name = column_name+" "+str(le.classes_[ii])
            df[this_column_name] = new_column[:,ii]

    return df, trained_transformers



def handle_data_files(infile_name):
    """
    For a given infile name, open the file into a 
    pandas Dataframe and determinately split into training
    and testing subsets. Save those as
    `train_X.csv` and `test_X.csv` in the `datasets`
    directory (where `X` is the integer index of the
    dataset and should be present in infile_name)

    Params
    ------
    infile_name : str or list of str
        name of the input dataset, standard format
        is dataset_X.csv, where "X" is an integer index
        can also take a list of dataset names and will
        concatenate the datasets in that case
    
    Returns
    -------
    train_df, pd.DataFrame
        80% of input data, for training
    test_df, pd.DataFrame
        20% of input data, for testing
    """
    # assume filename format: dataset_X.csv where
    # X is an integer that indexes the file
    if type(infile_name) is str:
        df = pd.read_csv(infile_name)
        dataset_id = infile_name.split(".csv")[0].split("_")[1]
        train_name = "../../datasets/train_{}.csv".format(dataset_id)
        test_name = "../../datasets/test_{}.csv".format(dataset_id)

    elif type(infile_name) is list:
        dfs = [pd.read_csv(ff) for ff in infile_name]
        dataset_ids = [ff.split(".csv")[0].split("_")[1] for ff in infile_name]
        train_name = "../../datasets/train_{}.csv".format(ii for ii in dataset_ids)
        test_name = "../../datasets/test_{}.csv".format(ii for ii in dataset_ids)
        df = pd.concat(dfs)

    train_file = Path(train_name)
    if train_file.is_file():
        logger.info("found {}, retrieving".format(train_name))
        train_df = pd.read_csv(train_name)
        test_df = pd.read_csv(test_name)
    else:
        logger.info("{} not found, creating".format(train_name))
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
        # index=False prevents an unwanted column named "Unnamed: 0"
        # from being appended 
        # https://stackoverflow.com/questions/36519086/pandas-how-to-get-rid-of-unnamed-column-in-a-dataframe
        train_df.to_csv(train_name, index=False)
        test_df.to_csv(test_name, index=False)

    return train_df, test_df


def encode_labels(df, col="status_group"):
    """
    Takes a df with an index and the status_group column
    filled with strings ("functional", "functional needs repair",
    "non-functional") and returns integer-encoded labels
    column

    Params
        df: pd.DataFrame

    Returns
        pd.DataFrame, with integer-encoded "status_group" column
    """
    labels = df[col].tolist()
    le = LabelEncoder()
    labels_encoded = le.fit_transform(labels)
    df[col] = labels_encoded
    logger.info("encoding labels complete")
    return df


def build_model(df_train):
    """
    Build a model with df_train as the training data.
    
    Params
    ------
    df_train, pd.DataFrame
        training dataset

    Returns
    -------
    sklearn.ModelPipeline
        trained model
    dict of dicts of LabelEncoder, OneHotEncoder
        transformers for doing feature dummying
    """
    
    df_y = df_train[["id", "status_group"]]
    data_y = encode_labels(df_y)["status_group"].tolist()
    
    df_train, tt = feature_preprocessing(df_train)
    df_X = df_train.drop("status_group", axis=1)
    data_X = df_X.as_matrix()   
 
    kbest = SelectKBest(k=100)
    rf = RandomForestClassifier(random_state=42)
    steps = [('feature_selection', kbest),
             ('random_forest', rf)]

    pipeline = Pipeline(steps)
    
    logger.info("attempting to fit model")
    pipeline.fit(data_X, data_y)

    return tt, pipeline


def run_predictions(model, tt, df_test):
    """
    Run predictions for the model on the test_df

    Params
    ------
    df_test, pd.DataFrame
        testing dataset

    Returns
    -------
    list of int
        class label predictions for test_df
    """
    # need to preprocess the features like
    # we did for the training dataset
    df_y = df_test[["id", "status_group"]]
    data_y = encode_labels(df_y)["status_group"].tolist()
    
    df_test, tt = feature_preprocessing(df_test, tt)
    df_X = df_test.drop("status_group", axis=1)
    data_X = df_X.as_matrix()   

    predictions = model.predict(data_X)

    return predictions


def evaluate_model(y_truth, y_pred):
    logger.info(classification_report(y_truth, y_pred))



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--files', type=str, 
                        help="comma-separated list of data file names"
                             " (will prepend the `datasets` directory part)")
    args = parser.parse_args()

    file_list = args.files.split(",")
    file_list = ["../../datasets/"+ii for ii in file_list]

    # model #1
    train_df, test_df = handle_data_files(file_list[0])
    
    tt, model = build_model(train_df)
    predictions = run_predictions(model, tt, test_df)
    
    logger.info(predictions)

    truth_y = encode_labels(test_df)["status_group"].tolist()
    evaluate_model(truth_y, predictions)



    # model #2
    train_df, test_df = handle_data_files(file_list)
    
    tt, model = build_model(train_df)
    predictions_2 = run_predictions(model, tt, test_df)
    
    logger.info(predictions)

    truth_y_2 = encode_labels(test_df)["status_group"].tolist()
    evaluate_model(truth_y_2, predictions_2)
    logger.info("All done!")


    # compare model predictions
    # only the first half of test examples can be meaningfully
    # compared
    ctr = 0
    logger.info("listing event number for cases that were"
                "'functional needs repair' that the first model"
                "missed but the second model caught")
    for p1, p2 in zip(predictions, predictions_2):
        # are we picking up class 1 predictions from dataset 1?
        if p1!=1 and p2==1:
            logger.info(ctr)
        ctr += 1


if __name__=="__main__":
    main()
