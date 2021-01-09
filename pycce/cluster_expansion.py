import functools
import operator

import numpy as np

from .sm import _smc


def cluster_expansion_decorator(_func=None, *, result_operator=operator.imul, contribution_operator=operator.ipow):
    """
    Decorator for creating cluster correlation expansion. Each expanded function will have two first arguments:
    subclusters and allnspin
    @param _func: function to expand
    @param result_operator: function
        operator which will combine the result of expansion (default: operator.imul)
    @param contribution_operator: function
        operator which will combine multiple contributions
        of the same cluster (default: operator.ipow)
    @return: function
    """

    def inner_cluster_expansion_decorator(function):

        @functools.wraps(function)
        def cluster_expansion(subclusters, allspin, *arg, **kwarg):
            """
            Inner part of cluster expansion. 
            @param subclusters: dict
                dict of subclusters included in different CCE order
                of structure {int order: np.array([[i,j],[i,j]])}
            @param allspin: ndarray
                array of atoms

            @param arg:
                all additional arguments
            @param kwarg:
                all additional keyword arguments
            @return:
            """
            revorders = sorted(subclusters)[::-1]
            norders = len(revorders)

            # If there is only one set of indexes for only one order,
            # Then for this subcluster nelements < maximum CCE order
            if norders == 1 and subclusters[revorders[0]].shape[0] == 1:
                verticles = subclusters[revorders[0]][0]

                return function(verticles, allspin, *arg, **kwarg)

            result = 1
            result = contribution_operator(result, 0)
            # The Highest possible L will have all powers of 1
            power = {}
            # Number of visited orders from highest to lowest
            visited = 0
            for order in revorders:
                power[order] = np.ones(subclusters[order].shape[0], dtype=np.int32)
                # indexes of the cluster of size order are stored in v

                for index in range(subclusters[order].shape[0]):

                    v = subclusters[order][index]
                    # First, find the correct power. Iterate over all higher orders
                    for higherorder in revorders[:visited]:
                        # np.isin gives bool array of shape subclusters[higherorder],
                        # which is np.array of
                        # indexes of subclusters with order = higherorder.
                        # Entries are True if value is
                        # present in v and False if values are not present in v.
                        # Sum bool entries in inside cluster,
                        # if the sum equal to size of v,
                        # then v is inside the given subcluster.
                        # containv is 1D bool array with values of i-element True
                        # if i-subcluster of
                        # subclusters[higherorder] contains v
                        containv = np.count_nonzero(
                            np.isin(subclusters[higherorder], v), axis=1) == v.size

                        # Power of cluster v is decreased by sum of powers of all the higher orders,
                        # As all of them have to be divided by v
                        power[order][index] -= np.sum(power[higherorder]
                                                      [containv], dtype=np.int32)

                    vcalc = function(v, allspin, *arg, **kwarg)

                    vcalc = contribution_operator(vcalc, power[order][index])

                    result = result_operator(result, vcalc)

                visited += 1
                # print('Computed {} of order {} for {} clusters'.format(
                #     function.__name__, order, subclusters[order].shape[0]))
            _smc.clear()

            return result

        return cluster_expansion

    if _func is None:
        return inner_cluster_expansion_decorator
    else:
        return inner_cluster_expansion_decorator(_func)


def cluster_expansion_direct_decorator(_func=None, *, result_operator=operator.imul,
                                       removal_operator=operator.itruediv,
                                       addition_operator=np.prod):
    """
    Decorator for creating cluster correlation expansion. Each expanded function will have two first arguments:
    subclusters and allnspin
    @param _func: function to expand
    @param result_operator: function
        operator which will combine the result of expansion (default: operator.imul)
    @param contribution_operator: function
        operator which will combine multiple contributions
        of the same cluster (default: operator.ipow)
    @param removal_operator: function
        operator which will act on L and remove all L tildas from given L
        in direct approach (default operator.itruediv)
    @param addition_operator: function
        operator which will combine the L tildas of all subclusters of lower order
        in direct approach (default np.prod)
    @param direct: whether to use direct approach or not
    @return: function
    """

    def inner_cluster_expansion_decorator_direct_method(function):

        @functools.wraps(function)
        def cluster_expansion(subclusters, allnspin, *arg, **kwarg):
            """
            Inner part of cluster expansion.
            @param subclusters: dict
                dict of subclusters included in different CCE order
                of structure {int order: np.array([[i,j],[i,j]])}
            @param allnspin: ndarray
                array of atoms

            @param arg:
                all additional arguments
            @param kwarg:
                all additional keyward
            @return:
            """

            orders = sorted(subclusters)
            norders = len(orders)

            # print(dms_zero.mask)
            # If there is only one set of indexes for only one order,
            # Then for this subcluster nelements < maximum CCE order
            if norders == 1 and subclusters[orders[0]].shape[0] == 1:
                verticles = subclusters[orders[0]][0]

                return function(allnspin[verticles], *arg, **kwarg)

                # print(zero_power)
            # The Highest possible L will have all powers of 1
            result_tilda = {}
            visited = 0
            result = 1 - result_operator(1, 0)

            for order in orders:
                result_tilda[order] = []
                # indexes of the cluster of size order are stored in v

                for index in range(subclusters[order].shape[0]):

                    v = subclusters[order][index]
                    vcalc = function(allnspin[v], *arg, **kwarg)

                    for lowerorder in orders[:visited]:
                        contained_in_v = np.all(np.isin(subclusters[lowerorder], v), axis=1)
                        lower_vcalc = addition_operator(result_tilda[lowerorder][contained_in_v], axis=0)
                        vcalc = removal_operator(vcalc, lower_vcalc)

                    result = result_operator(result, vcalc)

                    result_tilda[order].append(vcalc)

                result_tilda[order] = np.array(result_tilda[order], copy=False)

                visited += 1

            return result

        return cluster_expansion

    if _func is None:
        return inner_cluster_expansion_decorator_direct_method
    else:
        return inner_cluster_expansion_decorator_direct_method(_func)
