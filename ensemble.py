import numpy as np
import heapq as hq
from skmultiflow.trees import HoeffdingTree
from skmultiflow.bayes import NaiveBayes
import operator


class WeightedEnsembleClassifier:
    """The classifier that follows the rules of Weighted Ensemble Classifier"""

    class WeightedClassifier:
        """
        An inner class that eases the control of weights and crazy shit
        """

        def __init__(self, clf, weight, chunk_labels):
            """
            Create a new weighted classifier
            :param clf: the already trained classifier
            :param weight: the weight associated to it
            :param chunk_labels: the unique labels of the data chunk clf is trained on
            """
            self.clf = clf # the model
            self.weight = weight # the weight associated to this classifier
            self.chunk_labels = chunk_labels # the unique labels of the data chunk the classifier is trained on

        def __lt__(self, other):
            """
            Compares an object of this class to the other, by means of its weight.
            This method helps the heap to sort the classifier correctly

            :param other: the other object of this class
            :return: true i.e. this object is smaller than the other object by means of their weight
            """
            return self.weight < other.weight


    def __init__(self, K=10, learner="tree"):
        """
        Create a new ensemble
        :param K:       the maximum number of models allowed in this ensemble
        :param learner: indicates the weak/individual learners in the ensemble,
                        possible choices are: "tree" for Hoeffding tree,
                        "bayes" for Naive Bayes
                        TODO have RIPPER also ? https://algorithmia.com/algorithms/weka/JRip
        """

        # top K classifiers
        self.K = K

        # base learner
        self.base_learner = learner

        # a heap of weighted classifier
        # s.t. the 1st element is the classifier with the smallest weight (worst one)
        self.models = []


    def partial_fit(self, X, y=None, classes=None, weight=None):
        """
        Fit the ensemble to a data chunk
        Implement the basic Algorithm 1 as described in the paper

        :param X: the training data (a data chunk S)
        :param y: the training labels
        :param classes: array-like, contains all possible labels,
                        if not provided, it will be derived from y
        :param weight:  array-like, instance weight
                        if not provided, uniform weights are assumed
        :return: self
        """

        # if the classes are not provided, we derive it from y
        N, D = X.shape
        class_count = None # avoid calling unique multiple times
        if classes is None:
            classes, class_count = np.unique(y, return_counts=True)

        # (1) train classifier C' from X
        # allows a wider variety of classifiers
        # not a lot but still...
        if self.base_learner == "bayes": # Naive Bayes
            C_new = NaiveBayes()
        else: # by default, set to Hoeffding Tree
            C_new = HoeffdingTree()

        C_new.partial_fit(X, y, classes=classes)

        # (2) compute error rate/benefit of C_new via cross-validation on S

        # MSE_r: compute the baseline error rate given by a random classifier
        # a. class distribution learnt from the data
        # use this improve the performance
        if class_count is None:
            _, class_count = np.unique(classes, return_counts=True)
        class_dist = [class_count[i] / N for i, c in enumerate(classes)]
        MSE_r = np.sum([class_dist[i] * ((1 - class_dist[i]) ** 2) for i, c in enumerate(classes)])

        # b. assumption: uniform distribution
        # p_c = 1/L
        # MSE_r = L * (p_c * ((1 - p_c) ** 2))

        # MSE_i: compute the error rate of C_new via cross-validation on X
        # f_ic = the probability given by C_new that x is an instance of class c
        MSE_i = self.compute_MSE(y, C_new.predict_proba(X), classes)

        # (3) derive weight w_new for C_new using (8) or (9)
        w_new = MSE_r - MSE_i

        # create a new classifier with its associated weight,
        # the unique labels of the data chunk it is trained on
        clf_new = self.WeightedClassifier(clf=C_new, weight=w_new, chunk_labels=classes)

        # (4) update the weights of each classifier in the ensemble
        for i, clf in enumerate(self.models):
            MSE_i = self.compute_MSE(y, clf.clf.predict_proba(X), clf.chunk_labels) # apply Ci on S to derive MSE_i
            clf.weights = MSE_r - MSE_i # update wi based on (8) or (9)

        # (5) C <- top K weighted classifiers in C U { C' }
        # selecting top K models by dropping the worst model i.e. clf with smallest weight in C U { C' }
        if len(self.models) < self.K:
            # just push the new model in if there is still slots
            hq.heappush(self.models, clf_new)
        else:
            # if the new model has a weight > that of the bottom classifier (worst one)
            if clf_new.weight > self.models[0].weight:
                hq.heappushpop(self.models, clf_new) # push the new classifier and remove the bottom one
            # do nothing if the new model has a weight even lower than that of the worst classifier

        return self


    def predict(self, X):
        """
        Predicts the labels of X in a multiClass classification setting
        The prediction is done via weighted voting (choosing the maximum)

        :return: a list containing predictions
        """

        # List with size X.shape[0] and each value is a dict too,
        # Ex: [{0:0.2, 1:0.7}, {1:0.3, 2:0.5}]
        list_label_instance = []

        # For each classifier in self.models, predict the labels for X
        for model in self.models:
            clf = model.clf
            pred = clf.predict(X)
            weight = model.weight
            for i, label in enumerate(pred.tolist()):
                if i == len(list_label_instance): # maintain the dictionary
                    list_label_instance.append({label: weight})
                else:
                    try:
                        list_label_instance[i][label] += weight
                    except:
                        list_label_instance[i][label] = weight

        predict_weighted_voting = []
        for dic in list_label_instance:
            max_value = max(dic.items(), key=operator.itemgetter(1))[0] # return the key of max value in a dict
            predict_weighted_voting.append(max_value)

        return predict_weighted_voting


    def compute_MSE(self, y, probabs, labels):
        """
        Compute the mean square error of a classifier, via the predicted probabilities.

        It is a bit tricky here:
        - Suppose that we have a dataset D with 7 labels D_L = [1 2 3 4 5 6 7]; |D_L| = 7
        - We have a classifier C trained on a chunk of data S where |S| << |D|
        and in S we only see 4 labels S_L = [1 3 4 6] appear; |S_L| = 4
        - After being trained, C is able to predict the probability that an example
        has a label that appears in S_L i.e. the result of C.predict_proba(S)
        is an array of shape (|S|, 4) instead of (|S|, 7)
        - Now we want to use C to predict the label probability of a new chunk of data S',
        and S' may have only 2 unique labels appear in it (for example S'_L = [1 2]), so
        for an example in S', if we want to ask for the probability of the label 2, C cannot
        give it to us because it has not seen this label 2 when it is trained on the chunk S.
        If such case appears we simply set the probability of the missing label to 0

        This code needs to take into account the fact that a classifier C trained previously
        on a chunk of data does not yield the probabilities that correspond to another chunk of data

        :param y: the true labels
        :param probabs: the predicted probability
        :param labels: the unique labels associated to the classifier that gives this predicted probability
        :return: the mean square error MSE_i
        """
        N = len(y)
        sum_error = 0
        for i, c in enumerate(y):
            # if the label in y is unseen when training, skip it, don't include it in the error
            if c in labels:
                index_label_c = np.where(labels == c)[0][0]  # find the index of this label c in probabs[i]
                probab_ic = probabs[i][index_label_c]
                sum_error += (1 - probab_ic) ** 2

        return (sum_error / N)