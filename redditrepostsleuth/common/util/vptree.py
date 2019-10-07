""" This module contains an implementation of a Vantage Point-tree (VP-tree)."""
import numpy as np

from redditrepostsleuth.common.logging import log
from datetime import datetime

class VPTree:
    """ VP-Tree data structure for efficient nearest neighbor search.

    The VP-tree is a data structure for efficient nearest neighbor
    searching and finds the nearest neighbor in O(log n)
    complexity given a tree constructed of n data points. Construction
    complexity is O(n log n).

    Parameters
    ----------
    points : Iterable
        Construction points.
    dist_fn : Callable
        Function taking to point instances as arguments and returning
        the distance between them.
    leaf_size : int
        Minimum number of points in leaves (IGNORED).
    """

    def __init__(self, points, dist_fn):
        self.left = None
        self.right = None
        self.left_min = np.inf
        self.left_max = 0
        self.right_min = np.inf
        self.right_max = 0
        self.dist_fn = dist_fn
        self.built_at = datetime.now()

        if not len(points):
            raise ValueError('Points can not be empty.')
        #log.debug('Building VP tree with %s points', len(points))

        # Vantage point is point furthest from parent vp.
        vp_i = 0
        self.vp = points[vp_i]
        points = np.delete(points, vp_i, axis=0)

        if len(points) == 0:
            return

        # Choose division boundary at median of distances.
        distances = [self.dist_fn(self.vp.image_hash, p.image_hash) for p in points]
        median = np.median(distances)

        left_points = []
        right_points = []
        for point, distance in zip(points, distances):
            if distance >= median:
                self.right_min = min(distance, self.right_min)
                if distance > self.right_max:
                    self.right_max = distance
                    right_points.insert(0, point)  # put furthest first
                else:
                    right_points.append(point)
            else:
                self.left_min = min(distance, self.left_min)
                if distance > self.left_max:
                    self.left_max = distance
                    left_points.insert(0, point)  # put furthest first
                else:
                    left_points.append(point)

        if len(left_points) > 0:
            self.left = VPTree(points=left_points, dist_fn=self.dist_fn)

        if len(right_points) > 0:
            self.right = VPTree(points=right_points, dist_fn=self.dist_fn)

    def _is_leaf(self):
        return (self.left is None) and (self.right is None)

    def get_nearest_neighbor(self, query):
        """ Get single nearest neighbor.

        Parameters
        ----------
        query : Any
            Query point.

        Returns
        -------
        Any
            Single nearest neighbor.
        """
        return self.get_n_nearest_neighbors(query, n_neighbors=1)[0]

    def get_n_nearest_neighbors(self, query, n_neighbors):
        """ Get `n_neighbors` nearest neigbors to `query`

        Parameters
        ----------
        query : Any
            Query point.
        n_neighbors : int
            Number of neighbors to fetch.

        Returns
        -------
        list
            List of `n_neighbors` nearest neighbors.
        """
        if not isinstance(n_neighbors, int) or n_neighbors < 1:
            raise ValueError('n_neighbors must be strictly positive integer')
        neighbors = _AutoSortingList(max_size=n_neighbors)
        nodes_to_visit = [(self, 0)]

        furthest_d = np.inf

        while len(nodes_to_visit) > 0:
            node, d0 = nodes_to_visit.pop(0)
            if node is None or d0 > furthest_d:
                continue

            d = self.dist_fn(query, node.vp.image_hash)
            if d < furthest_d:
                neighbors.append((d, node.vp))
                furthest_d, _ = neighbors[-1]

            if node._is_leaf():
                continue

            if node.left_min <= d <= node.left_max:
                nodes_to_visit.insert(0, (node.left, 0))
            elif node.left_min - furthest_d <= d <= node.left_max + furthest_d:
                nodes_to_visit.append((node.left,
                                       node.left_min - d if d < node.left_min
                                       else d - node.left_max))

            if node.right_min <= d <= node.right_max:
                nodes_to_visit.insert(0, (node.right, 0))
            elif node.right_min - furthest_d <= d <= node.right_max + furthest_d:
                nodes_to_visit.append((node.right,
                                       node.right_min - d if d < node.right_min
                                       else d - node.right_max))

        return list(neighbors)

    def get_all_in_range(self, query, max_distance):
        """ Find all neighbours within `max_distance`.

        Parameters
        ----------
        query : Any
            Query point.
        max_distance : float
            Threshold distance for query.

        Returns
        -------
        neighbors : list
            List of points within `max_distance`.

        Notes
        -----
        Returned neighbors are not sorted according to distance.
        """
        neighbors = list()
        nodes_to_visit = [(self, 0)]

        while len(nodes_to_visit) > 0:
            node, d0 = nodes_to_visit.pop(0)
            if node is None or d0 > max_distance:
                continue

            d = self.dist_fn(query, node.vp.image_hash)
            if d < max_distance:
                neighbors.append((d, node.vp))

            if node._is_leaf():
                continue
            if node.left_min <= d <= node.left_max:
                nodes_to_visit.insert(0, (node.left, 0))
            elif node.left_min - max_distance <= d <= node.left_max + max_distance:
                nodes_to_visit.append((node.left,
                                       node.left_min - d if d < node.left_min
                                       else d - node.left_max))

            if node.right_min <= d <= node.right_max:
                nodes_to_visit.insert(0, (node.right, 0))
            elif node.right_min - max_distance <= d <= node.right_max + max_distance:
                nodes_to_visit.append((node.right,
                                       node.right_min - d if d < node.right_min
                                       else d - node.right_max))

        return neighbors


class _AutoSortingList(list):
    """ Simple auto-sorting list.

    Inefficient for large sizes since the queue is sorted at
    each push.

    Parameters
    ---------
    size : int, optional
        Max queue size.
    """
    def __init__(self, max_size=None, *args):
        super(_AutoSortingList, self).__init__(*args)
        self.max_size = max_size

    def append(self, item):
        """ Append `item` and sort.

        Parameters
        ----------
        item : Any
            Input item.
        """
        super(_AutoSortingList, self).append(item)
        self.sort()
        if self.max_size is not None and len(self) > self.max_size:
            self.pop()

