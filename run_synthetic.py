# coding: utf8
"""
Run file to run kNN experiments on synthethic problems. Problems are created
using the synthethic problem factory.
"""
# coding: utf8
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import json
# I/O import
import os
import shutil
import sys
import tempfile
import time

# Specific imports
import numpy as np
# For parallelization
from sklearn.model_selection import ParameterGrid

from synthethic_problem_factory.curves import *
from synthethic_problem_factory.functions_on_manifolds import (RandomPolynomialIncrements,
                                                               randomPolynomialIncrements_for_parallel)
from synthethic_problem_factory.sample_synthetic_data import sample_1D_fromClass_lesser

# Score functions
def MSE(prediction, reference):
    return np.sum(np.linalg.norm(prediction - reference, axis = 0) ** 2)/ \
                np.sum(np.linalg.norm(reference, axis = 0) ** 2)

def RMSE(prediction, reference):
    """ Root Mean squared error """
    return np.sqrt(MSE(prediction, reference))

def UAE(prediction, reference):
    """ Uniform absolute error max_i |v_i - hat v_i| """
    return np.max(np.linalg.norm(prediction - reference, axis = 0))

def run_example(n_samples,
                ambient_dim,
                noise,
                var_f,
                random_seeds,
                manifold,
                f_on_manifold,
                estimator,
                rep, i1, i2, i3, i4, # Indices to write into
                args_f = None):
    """
    Main function to run a single experiment. Saves the results into the
    given files. The test manifold is set below.
    """
    assert 'options' in estimator, "MAIN: No 'options' key in estimator dict"
    # Check if crossvalidation is done
    CV_split = estimator['options'].get('CV_split', 0.0)
    np.random.seed(random_seeds[i1, i2, i3, i4, rep])
    # Setting the test manifold, check synthethic_problem_factory.curves
    manifold = get_manifold(ambient_dim, **manifold)
    # Split n_samples into training and CV
    n_samples_CV = np.floor(CV_split * n_samples).astype('int')
    n_samples_train = n_samples - n_samples_CV
    # Get training samples
    all_pdisc, all_points, all_fval = sample_1D_fromClass_lesser(manifold,
                                                            f_on_manifold,
                                                            n_samples,
                                                            noise,
                                                            var_f = var_f,
                                                            tube = 'l2',
                                                            args_f = args_f)
    # Extract training and CV set
    pdisc, points, fval = all_pdisc[:n_samples_train], all_points[:,:n_samples_train], all_fval[:n_samples_train]
    points_CV, fval_CV = all_points[:,n_samples_train:], all_fval[n_samples_train:]
    del all_pdisc, all_points, all_fval
    # Get test samples
    n_test_samples = 1000
    _, points_test, fval_test = sample_1D_fromClass_lesser(manifold,f_on_manifold,
                                                            n_test_samples, noise,
                                                            var_f = 0.00,
                                                            tube = 'l2',
                                                            args_f = args_f)
    print("Finished N = {0}     D = {1}     sigma = {2}     sigma_f = {3}   rep = {4}".format(
        n_samples, ambient_dim, noise, var_f, rep))
    return pdisc, points, fval, points_CV, fval_CV, points_test, fval_test

if __name__ == "__main__":
    # Get number of jobs from sys.argv
    if len(sys.argv) > 1:
        n_jobs = int(sys.argv[1])
    else:
        n_jobs = 1 # Default 1 jobs
    print('Using n_jobs = {0}'.format(n_jobs))
    # Define manifolds to test
    manifolds = [{'start' : 0, 'end' : 1.0, 'manifold_id' : 'identity'},
                {'start' : 0, 'end' : np.pi, 'manifold_id' : 'scurve'},
                {'start' : 0, 'end' : 2.0 * np.pi, 'manifold_id' : 'helix'}]
    for manifold in manifolds:
        # Sample random function, or load if already exist
        if not os.path.exists('random_polynomials/random_polynomial_for_' + manifold['manifold_id'] + '.npz'):
            fun_obj = RandomPolynomialIncrements(manifold['start'], manifold['end'], 2, 100,
                                                 coefficient_bound = [1.0, 1.5])
            bases = fun_obj.get_bases()
            coeffs = fun_obj.get_coeffs()
            np.savez('random_polynomials/random_polynomial_for_' + manifold['manifold_id'] + '.npz', bases = bases, coeffs = coeffs)
        else:
            data = np.load('random_polynomials/random_polynomial_for_' + manifold['manifold_id'] + '.npz')
            bases = data['bases']
            coeffs = data['coeffs']
        print("Considering manifold {0}".format(manifold['manifold_id']))
        # Parameters
        run_for = {
            'N' : [2000,4000,8000,16000],#[200 * (2 ** i) for i in range(13)],
            'D' : [4,8,16],
            'sigma_X' : [0.25],
            'sigma_f' : [0.0],#, 1e-4, 1e-3, 1e-2, 1e-1],
            'repititions' : 5,#20,
            # Estimator information
            'estimator' : {
                'estimator_id' : 'nsim',
                'options' : {
                    'split_by' : 'stateq',
                    'CV_split' : 0.1,
                    'noisefree_levelset_fac' : 15,
                    'n_neighbors' : [0.5]
                },
                'params' : {
                    'n_levelsets' : [1 * (2 ** i) for i in range(14)],
                    'ball_radius' : [0.5],
                }
            }
        }
        parametergrid = ParameterGrid(run_for['estimator']['params'])
        random_seeds = np.random.randint(0, high = 2**32 - 1, size = (len(run_for['N']),
                                                              len(run_for['D']),
                                                              len(run_for['sigma_X']),
                                                              len(run_for['sigma_f']),
                                                              run_for['repititions']))
        savestr_base = '/run_3'
        filename_errors = 'results/' + manifold['manifold_id'] + '/' + run_for['estimator']['estimator_id'] + savestr_base
        if not os.path.exists(filename_errors):
            os.makedirs(filename_errors)
            # Save a log file
        with open(filename_errors + '/log.txt', 'w') as file:
            file.write(json.dumps(run_for, indent=4)) # use `json.loads` to do the reverse
        tmp_folder = tempfile.mkdtemp()
        try:
            #skip running the estimator and just save the data
            for rep in range(run_for['repititions']):
                for i4 in range(len(run_for['sigma_f'])):
                    for i2 in range(len(run_for['D'])):
                        for i3 in range(len(run_for['sigma_X'])):
                            starttime = time.time()
                            for i1 in range(len(run_for['N'])):
                                pdisc, points, fval, points_CV, fval_CV, points_test, fval_test = run_example(
                                    run_for['N'][i1],
                                    run_for['D'][i2],
                                    run_for['sigma_X'][i3],
                                    run_for['sigma_f'][i4],
                                    random_seeds,
                                    manifold,
                                    randomPolynomialIncrements_for_parallel,
                                    run_for['estimator'],
                                    rep, i1, i2, i3, i4,
                                    args_f = (bases, coeffs))
                                print(pdisc.shape, points.shape, fval.shape, points_CV.shape, fval_CV.shape, points_test.shape, fval_test.shape)
                                paramstr = f"{manifold['manifold_id']}rep{rep}N{run_for['N'][i1]}D{run_for['D'][i2]}sigX{run_for['sigma_X'][i3]}sigf{run_for['sigma_f'][i4]}"
                                print(paramstr)
                                np.savez("syntheticdata"+paramstr,
                                            pdisc=pdisc, 
                                            points=points, 
                                            fval=fval, 
                                            points_CV=points_CV, 
                                            fval_CV=fval_CV, 
                                            points_test=points_test, 
                                            fval_test=fval_test)
                                print(time.time() - starttime) # i estimate that without any parallelization this will finish in ~20 hours
        finally:
            try:
                shutil.rmtree(tmp_folder)
            except:
                print('Failed to delete: ' + tmp_folder)
