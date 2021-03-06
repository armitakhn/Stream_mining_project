from ensemble import WeightedEnsembleClassifier
from costsensiv_ensemble import CostSensitiveWeightedEnsembleClassifier
from skmultiflow.data.file_stream import FileStream
from skmultiflow.evaluation.evaluate_prequential import EvaluatePrequential

# prepare the stream
# reuse the electricity stream for test
path_data = 'data/'
stream = FileStream(path_data + 'elec.csv', n_targets=1, target_idx=-1)
stream.prepare_for_use()

# instantiate a classifier
# clf = CostSensitiveWeightedEnsembleClassifier()
clf = WeightedEnsembleClassifier(K=10, learner="tree")

evaluator = EvaluatePrequential(pretrain_size=1000, max_samples=20000, show_plot=True,
                                metrics=['accuracy', 'kappa'], output_file='result.csv',
                                batch_size=10) # I set the batch size to 10

# 4. Run
evaluator.evaluate(stream=stream, model=clf)