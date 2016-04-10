# -*- coding: utf-8 -*-
"""
hdbscan.plots: Use matplotlib to display plots of internal 
               tree structures used by HDBSCAN.
"""
# Author: Leland McInnes <leland.mcinnes@gmail.com>
#
# License: BSD 3 clause

import numpy as np

from scipy.cluster.hierarchy import dendrogram
from sklearn.manifold import TSNE
from sklearn.decomposition import PCA
from sklearn.metrics import pairwise_distances
from warnings import warn
from ._hdbscan_tree import compute_stability, labelling_at_cut

CB_LEFT = 0
CB_RIGHT = 1
CB_BOTTOM = 2
CB_TOP = 3


def _bfs_from_cluster_tree(tree, bfs_root):
    """
    Perform a breadth first search on a tree in condensed tree format
    """

    result = []
    to_process = [bfs_root]

    while to_process:
        result.extend(to_process)
        to_process = tree['child'][np.in1d(tree['parent'], to_process)].tolist()

    return result

def _recurse_leaf_dfs(cluster_tree, current_node):
    children = cluster_tree[cluster_tree['parent'] == current_node]['child']
    if len(children) == 0:
        return [current_node,]
    else:
        return sum([_recurse_leaf_dfs(cluster_tree, child) for child in children], [])

def _get_leaves(condensed_tree):
    cluster_tree = condensed_tree[condensed_tree['child_size'] > 1]
    root = cluster_tree['parent'].min()
    return _recurse_leaf_dfs(cluster_tree, root)

def _bfs_from_linkage_tree(hierarchy, bfs_root):
    """
    Perform a breadth first search on a tree in scipy hclust format.
    """

    dim = hierarchy.shape[0]
    max_node = 2 * dim
    num_points = max_node - dim + 1

    to_process = [bfs_root]
    result = []

    while to_process:
        result.extend(to_process)
        to_process = [x - num_points for x in
                      to_process if x >= num_points]
        if to_process:
            to_process = hierarchy[to_process, :2].flatten().astype(np.int64).tolist()

    return result


class CondensedTree(object):
    def __init__(self, condensed_tree_array):
        self._raw_tree = condensed_tree_array

    def get_plot_data(self, leaf_separation=1, log_size=False):
        """Generates data for use in plotting the 'icicle plot' or dendrogram 
        plot of the condensed tree generated by HDBSCAN.

        Parameters
        ----------
        leaf_separation : float, optional
                          How far apart to space the final leaves of the 
                          dendrogram. (default 1)

        log_size : boolean, optional
                   Use log scale for the 'size' of clusters (i.e. number of
                   points in the cluster at a given lambda value).
                   (default False)
        
        Returns
        -------
        plot_data : dict
                    Data associated to bars in a bar plot:
                        `bar_centers` x coordinate centers for bars
                        `bar_tops` heights of bars in lambda scale
                        `bar_bottoms` y coordinate of bottoms of bars
                        `bar_widths` widths of the bars (in x coord scale)
                        `bar_bounds` a 4-tuple of [left, right, bottom, top]
                                     giving the bounds on a full set of 
                                     cluster bars
                    Data associates with cluster splits:
                        `line_xs` x coordinates for horiontal dendrogram lines
                        `line_ys` y coordinates for horiontal dendrogram lines
        """
        leaves = _get_leaves(self._raw_tree)
        last_leaf = self._raw_tree['parent'].max()
        root = self._raw_tree['parent'].min()

        # We want to get the x and y coordinates for the start of each cluster
        # Initialize the leaves, since we know where they go, the iterate
        # through everything from the leaves back, setting coords as we go
        cluster_x_coords = dict(zip(leaves, [leaf_separation * x
                                             for x in range(len(leaves))]))
        cluster_y_coords = {root: 0.0}

        for cluster in range(last_leaf, root - 1, -1):
            split = self._raw_tree[['child', 'lambda_val']]
            split = split[(self._raw_tree['parent'] == cluster) &
                          (self._raw_tree['child_size'] > 1)]
            if len(split['child']) > 1:
                left_child, right_child = split['child']
                cluster_x_coords[cluster] = np.mean([cluster_x_coords[left_child],
                                                     cluster_x_coords[right_child]])
                cluster_y_coords[left_child] = split['lambda_val'][0]
                cluster_y_coords[right_child] = split['lambda_val'][1]

        # We use bars to plot the 'icicles', so we need to generate centers, tops, 
        # bottoms and widths for each rectangle. We can go through each cluster 
        # and do this for each in turn.
        bar_centers = []
        bar_tops = []
        bar_bottoms = []
        bar_widths = []

        cluster_bounds = {}

        scaling = np.sum(self._raw_tree[self._raw_tree['parent'] == root]['child_size'])

        if log_size:
            scaling = np.log(scaling)

        for c in range(last_leaf, root - 1, -1):

            cluster_bounds[c] = [0, 0, 0, 0]

            c_children = self._raw_tree[self._raw_tree['parent'] == c]
            current_size = np.sum(c_children['child_size'])
            current_lambda = cluster_y_coords[c]

            if log_size:
                current_size = np.log(current_size)

            cluster_bounds[c][CB_LEFT] = cluster_x_coords[c] * scaling - (current_size / 2.0)
            cluster_bounds[c][CB_RIGHT] = cluster_x_coords[c] * scaling + (current_size / 2.0)
            cluster_bounds[c][CB_BOTTOM] = cluster_y_coords[c]
            cluster_bounds[c][CB_TOP] = np.max(c_children['lambda_val'])

            for i in np.argsort(c_children['lambda_val']):
                row = c_children[i]
                if row['lambda_val'] != current_lambda:
                    bar_centers.append(cluster_x_coords[c] * scaling)
                    bar_tops.append(row['lambda_val'] - current_lambda)
                    bar_bottoms.append(current_lambda)
                    bar_widths.append(current_size)
                if log_size:
                    current_size = np.log(np.exp(current_size) - row['child_size'])
                else:
                    current_size -= row['child_size']
                current_lambda = row['lambda_val']

        # Finally we need the horizontal lines that occur at cluster splits.
        line_xs = []
        line_ys = []

        for row in self._raw_tree[self._raw_tree['child_size'] > 1]:
            parent = row['parent']
            child = row['child']
            child_size = row['child_size']
            if log_size:
                child_size = np.log(child_size)
            sign = np.sign(cluster_x_coords[child] - cluster_x_coords[parent])
            line_xs.append([
                cluster_x_coords[parent] * scaling,
                cluster_x_coords[child] * scaling + sign * (child_size / 2.0)
            ])
            line_ys.append([
                cluster_y_coords[child],
                cluster_y_coords[child]
            ])

        return {
            'bar_centers': bar_centers,
            'bar_tops': bar_tops,
            'bar_bottoms': bar_bottoms,
            'bar_widths': bar_widths,
            'line_xs': line_xs,
            'line_ys': line_ys,
            'cluster_bounds': cluster_bounds
        }

    def _select_clusters(self):
        stability = compute_stability(self._raw_tree)
        node_list = sorted(stability.keys(), reverse=True)[:-1]
        cluster_tree = self._raw_tree[self._raw_tree['child_size'] > 1]
        is_cluster = {cluster: True for cluster in node_list}

        for node in node_list:
            child_selection = (cluster_tree['parent'] == node)
            subtree_stability = np.sum([stability[child] for
                                        child in cluster_tree['child'][child_selection]])

            if subtree_stability > stability[node]:
                is_cluster[node] = False
                stability[node] = subtree_stability
            else:
                for sub_node in _bfs_from_cluster_tree(cluster_tree, node):
                    if sub_node != node:
                        is_cluster[sub_node] = False

        return [cluster for cluster in is_cluster if is_cluster[cluster]]

    def plot(self, leaf_separation=1, cmap='Blues', select_clusters=False,
             label_clusters=False, axis=None, colorbar=True, log_size=False):
        """Use matplotlib to plot an 'icicle plot' dendrogram of the condensed tree.

        Effectively this is a dendrogram where the width of each cluster bar is
        equal to the number of points (or log of the number of points) in the cluster
        at the given lambda value. Thus bars narrow as points progressively drop
        out of clusters. The make the effect more apparent the bars are also colored
        according the the number of points (or log of the number of points).

        Parameters
        ----------
        leaf_separation : float, optional
                          How far apart to space the final leaves of the 
                          dendrogram. (default 1)

        cmap : string or matplotlib colormap, optional
               The matplotlib colormap to use to color the cluster bars.
               (default Blues)

        select_clusters : boolean, optional
                          Whether to draw ovals highlighting which cluster
                          bar represent the clusters that were selected by
                          HDBSCAN as the final clusters. (default False)

        label_clusters : boolean, optional
                         If select_clusters is True then this determines
                         whether to draw text labels on the clusters.

        axis : matplotlib axis or None, optional
               The matplotlib axis to render to. If None then a new axis
               will be generated. The rendered axis will be returned.
               (default None)

        colorbar : boolean, optional
                   Whether to draw a matplotlib colorbar displaying the range
                   of cluster sizes as per the colormap. (default True)

        log_size : boolean, optional
                   Use log scale for the 'size' of clusters (i.e. number of
                   points in the cluster at a given lambda value).
                   (default False)
           
        Returns
        -------
        axis : matplotlib axis
               The axis on which the 'icicle plot' has been rendered.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError(
                'You must install the matplotlib library to plot the condensed tree.'
                'Use get_plot_data to calculate the relevant data without plotting.')

        plot_data = self.get_plot_data(leaf_separation=leaf_separation, log_size=log_size)

        if cmap != 'none':
            sm = plt.cm.ScalarMappable(cmap=cmap,
                                       norm=plt.Normalize(0, max(plot_data['bar_widths'])))
            sm.set_array(plot_data['bar_widths'])
            bar_colors = [sm.to_rgba(x) for x in plot_data['bar_widths']]
        else:
            bar_colors = 'black'

        if axis is None:
            axis = plt.gca()

        axis.bar(
            plot_data['bar_centers'],
            plot_data['bar_tops'],
            bottom=plot_data['bar_bottoms'],
            width=plot_data['bar_widths'],
            color=bar_colors,
            align='center',
            linewidth=0
        )

        for xs, ys in zip(plot_data['line_xs'], plot_data['line_ys']):
            axis.plot(xs, ys, color='black', linewidth=1)
        if select_clusters:
            try:
                from matplotlib.patches import Ellipse
            except ImportError:
                raise ImportError('You must have matplotlib.patches available to plot selected clusters.')

            chosen_clusters = self._select_clusters()

            for i, c in enumerate(chosen_clusters):
                c_bounds = plot_data['cluster_bounds'][c]
                width = (c_bounds[CB_RIGHT] - c_bounds[CB_LEFT])
                height = (c_bounds[CB_TOP] - c_bounds[CB_BOTTOM])
                center = (
                    np.mean([c_bounds[CB_LEFT], c_bounds[CB_RIGHT]]),
                    np.mean([c_bounds[CB_TOP], c_bounds[CB_BOTTOM]]),
                )

                box = Ellipse(
                    center,
                    2.0 * width,
                    1.2 * height,
                    facecolor='none',
                    edgecolor='r',
                    linewidth=2
                )

                if label_clusters:
                    axis.annotate(str(i), xy=center,
                                  xytext=(center[0] - 4.0 * width, center[1] + 0.65 * height),
                                  horizontalalignment='left',
                                  verticalalignment='bottom')

                axis.add_artist(box)

        if colorbar:
            cb = plt.colorbar(sm)
            if log_size:
                cb.ax.set_ylabel('log(Number of points)')
            else:
                cb.ax.set_ylabel('Number of points')

        axis.set_xticks([])
        for side in ('right', 'top', 'bottom'):
            axis.spines[side].set_visible(False)
        axis.invert_yaxis()
        axis.set_ylabel('$\lambda$ value')

        return axis

    def to_numpy(self):
        """Return a numpy structured array representation of the condensed tree.
        """
        return self._raw_tree.copy()

    def to_pandas(self):
        """Return a pandas dataframe representation of the condensed tree.

        Each row of the dataframe corresponds to an edge in the tree.
        The columns of the dataframe are `parent`, `child`, `lambda_val`
        and `child_size`. 

        The `parent` and `child` are the ids of the
        parent and child nodes in the tree. Node ids less than the number 
        of points in the original dataset represent individual points, while
        ids greater than the number of points are clusters.

        The `lambda_val` value is the value (1/distance) at which the `child`
        node leaves the cluster.

        The `child_size` is the number of points in the `child` node.
        """
        try:
            from pandas import DataFrame, Series
        except ImportError:
            raise ImportError('You must have pandas installed to export pandas DataFrames')

        result = DataFrame(self._raw_tree)

        return result

    def to_networkx(self):
        """Return a NetworkX DiGraph object representing the condensed tree.

        Edge weights in the graph are the lamba values at which child nodes
        'leave' the parent cluster.

        Nodes have a `size` attribute attached giving the number of points
        that are in the cluster (or 1 if it is a singleton point) at the
        point of cluster creation (fewer points may be in the cluster at
        larger lambda values).
        """
        try:
            from networkx import DiGraph, set_node_attributes
        except ImportError:
            raise ImportError('You must have networkx installed to export networkx graphs')

        result = DiGraph()
        for row in self._raw_tree:
            result.add_edge(row['parent'], row['child'], weight=row['lambda_val'])

        set_node_attributes(result, 'size', dict(self._raw_tree[['child', 'child_size']]))

        return result


def _line_width(y, linkage):
    if y == 0.0:
        return 1.0
    else:
        return linkage[linkage.T[2] == y][0, 3]


class SingleLinkageTree(object):
    def __init__(self, linkage):
        self._linkage = linkage

    def plot(self, axis=None, truncate_mode=None, p=0, vary_line_width=True):
        """Plot a dendrogram of the single linkage tree.

        Parameters
        ----------
        truncate_mode : str, optional
                        The dendrogram can be hard to read when the original 
                        observation matrix from which the linkage is derived 
                        is large. Truncation is used to condense the dendrogram. 
                        There are several modes:

        ``None/'none'``
                No truncation is performed (Default).
    
        ``'lastp'``
                The last p non-singleton formed in the linkage are the only 
                non-leaf nodes in the linkage; they correspond to rows 
                Z[n-p-2:end] in Z. All other non-singleton clusters are 
                contracted into leaf nodes.

        ``'level'/'mtica'``
                No more than p levels of the dendrogram tree are displayed. 
                This corresponds to Mathematica(TM) behavior.

        p : int, optional
            The ``p`` parameter for ``truncate_mode``.

        vary_line_width : boolean, optional
            Draw downward branches of the dendrogram with line thickness that 
            varies depending on the size of the cluster.

        Returns
        -------
        axis : matplotlib axis
               The axis on which the dendrogram plot has been rendered.

        """
        dendrogram_data = dendrogram(self._linkage, p=p, truncate_mode=truncate_mode, no_plot=True)
        X = dendrogram_data['icoord']
        Y = dendrogram_data['dcoord']

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError('You must install the matplotlib library to plot the single linkage tree.')

        if axis is None:
            axis = plt.gca()

        if vary_line_width:
            linewidths = [(_line_width(y[0], self._linkage),
                           _line_width(y[1], self._linkage))
                          for y in Y]
        else:
            linewidths = [(1.0, 1.0)] * len(Y)

        for x, y, lw in zip(X, Y, linewidths):
            left_x = x[:2]
            right_x = x[2:]
            left_y = y[:2]
            right_y = y[2:]
            horizontal_x = x[1:3]
            horizontal_y = y[1:3]

            axis.plot(left_x, left_y, color='k', linewidth=np.log2(1 + lw[0]),
                      solid_joinstyle='miter', solid_capstyle='butt')
            axis.plot(right_x, right_y, color='k', linewidth=np.log2(1 + lw[1]),
                      solid_joinstyle='miter', solid_capstyle='butt')
            axis.plot(horizontal_x, horizontal_y, color='k', linewidth=1.0,
                      solid_joinstyle='miter', solid_capstyle='butt')

        axis.set_xticks([])
        for side in ('right', 'top', 'bottom'):
            axis.spines[side].set_visible(False)
        axis.set_ylabel('distance')

        return axis

    def to_numpy(self):
        """Return a numpy array representation of the single linkage tree.

        This representation conforms to the scipy.cluster.hierarchy notion
        of a single linkage tree, and can be used with all the associated
        scipy tools. Please see the scipy documentation for more details
        on the format.
        """
        return self._linkage.copy()


    def to_pandas(self):
        """Return a pandas dataframe representation of the single linkage tree.

        Each row of the dataframe corresponds to an edge in the tree.
        The columns of the dataframe are `parent`, `left_child`, 
        `right_child`, `distance` and `size`.

        The `parent`, `left_child` and `right_child` are the ids of the
        parent and child nodes in the tree. Node ids less than the number 
        of points in the original dataset represent individual points, while
        ids greater than the number of points are clusters.

        The `distance` value is the at which the child nodes merge to form
        the parent node.

        The `size` is the number of points in the `parent` node.
        """
        try:
            from pandas import DataFrame, Series
        except ImportError:
            raise ImportError('You must have pandas installed to export pandas DataFrames')

        max_node = 2 * self._linkage.shape[0]
        num_points = max_node - (self._linkage.shape[0] - 1)

        parent_array = np.arange(num_points, max_node + 1)

        result = DataFrame({
            'parent': parent_array,
            'left_child': self._linkage.T[0],
            'right_child': self._linkage.T[1],
            'distance': self._linkage.T[2],
            'size': self._linkage.T[3]
        })[['parent', 'left_child', 'right_child', 'distance', 'size']]

        return result

    def to_networkx(self):
        """Return a NetworkX DiGraph object representing the single linkage tree.

        Edge weights in the graph are the distance values at which child nodes
        merge to form the parent cluster.

        Nodes have a `size` attribute attached giving the number of points
        that are in the cluster.
        """
        try:
            from networkx import DiGraph, set_node_attributes
        except ImportError:
            raise ImportError('You must have networkx installed to export networkx graphs')

        max_node = 2 * self._linkage.shape[0]
        num_points = max_node - (self._linkage.shape[0] - 1)

        result = DiGraph()
        for parent, row in enumerate(self._linkage, num_points):
            result.add_edge(parent, row[0], weight=row[2])
            result.add_edge(parent, row[1], weight=row[2])

        size_dict = {parent: row[3] for parent, row in enumerate(self._linkage, num_points)}
        set_node_attributes(result, 'size', size_dict)

        return result

    def get_clusters(self, cut_distance, min_cluster_size=5):
        """Return a flat clustering from the single linkage hierarchy.

        This represents the result of selecting a cut value for robust single linkage
        clustering. The `min_cluster_size` allows the flat clustering to declare noise
        points (and cluster smaller than `min_cluster_size`).

        Parameters
        ----------

        cut_distance : float
            The mutual reachability distance cut value to use to generate a flat clustering.

        min_cluster_size : int, optional
            Clusters smaller than this value with be called 'noise' and remain unclustered
            in the resulting flat clustering.

        Returns
        -------

        labels : array [n_samples]
            An array of cluster labels, one per datapoint. Unclustered points are assigned
            the label -1.
        """
        return labelling_at_cut(self._linkage, cut_distance, min_cluster_size)


class MinimumSpanningTree(object):
    def __init__(self, mst, data):
        self._mst = mst
        self._data = data

    def plot(self, axis=None, node_size=10, node_color='k',
             node_alpha=0.5, edge_alpha=0.25, edge_cmap='Reds_r',
             edge_linewidth=2, vary_linewidth=True, colorbar=True):
        """Plot the minimum spanning tree (as projected into 2D by t-SNE if required).

        Parameters
        ----------

        axis : matplotlib axis, optional
               The axis to render the plot to

        node_size : int, optional
                The size of nodes in the plot (default 10).

        node_color : matplotlib color spec, optional
                The color to render nodes (default black).

        node_alpha : float, optional
                The alpha value (between 0 and 1) to render nodes with
                (default 0.5).

        edge_cmap : matplotlib colormap, optional
                The colormap to color edges by (varying color by edge 
                    weight/distance). Can be a cmap object or a string
                    recognised by matplotlib. (default `Reds_r`)

        edge_alpha : float, optional
                The alpha value (between 0 and 1) to render edges with
                (default 0.25).

        edge_linewidth : float, optional
                The linewidth to use for rendering edges (default 2).

        vary_linewidth : bool, optional
                Edge width is proportional to (log of) the inverse of the
                mutual reachability distance. (default True)

        colorbar : bool, optional
                Whether to draw a colorbar. (default True)

        Returns
        -------

        axis : matplotlib axis
                The axis used the render the plot.
        """
        try:
            import matplotlib.pyplot as plt
            from matplotlib.collections import LineCollection
        except ImportError:
            raise ImportError('You must install the matplotlib library to plot the minimum spanning tree.')

        if self._data.shape[0] > 32767:
            warn('Too many data points for safe rendering of an minimal spanning tree!')
            return None

        if axis is None:
            axis = plt.gca()

        if self._data.shape[1] > 2:
            # Get a 2D projection; if we have a lot of dimensions use PCA first
            if self._data.shape[1] > 32:
                # Use PCA to get down to 32 dimension
                data_for_projection = PCA(n_components=32).fit_transform(self._data)
            else:
                data_for_projection = self._data.copy()

            projection = TSNE().fit_transform(data_for_projection)
        else:
            projection = self._data.copy()

        if vary_linewidth:
            line_width = edge_linewidth * (np.log(self._mst.T[2].max() / self._mst.T[2]) + 1.0)
        else:
            line_width = edge_linewidth

        line_coords = projection[self._mst[:, :2].astype(int)]
        line_collection = LineCollection(line_coords, linewidth=line_width,
                                         cmap=edge_cmap, alpha=edge_alpha)
        line_collection.set_array(self._mst[:, 2].T)

        axis.add_artist(line_collection)
        axis.scatter(projection.T[0], projection.T[1], c=node_color, alpha=node_alpha, s=node_size)
        axis.set_xticks([])
        axis.set_yticks([])

        if colorbar:
            cb = plt.colorbar(line_collection)
            cb.ax.set_ylabel('Mutual reachability distance')

        return axis

    def to_numpy(self):
        """Return a numpy array of weighted edges in the minimum spanning tree
        """
        return self._mst.copy()

    def to_pandas(self):
        """Return a Pandas dataframe of the minimum spanning tree.

        Each row is an edge in the tree; the columns are `from`,
        `to`, and `distance` giving the two vertices of the edge
        which are indices into the dataset, and the distance
        between those datapoints.
        """
        try:
            from pandas import DataFrame
        except ImportError:
            raise ImportError('You must have pandas installed to export pandas DataFrames')

        result = DataFrame({'from': self._mst.T[0].astype(int),
                            'to': self._mst.T[1].astype(int),
                            'distance': self._mst.T[2]})
        return result

    def to_networkx(self):
        """Return a NetworkX Graph object representing the minimum spanning tree.

        Edge weights in the graph are the distance between the nodes they connect.

        Nodes have a `data` attribute attached giving the data vector of the
        associated point.
        """
        try:
            from networkx import Graph, set_node_attributes
        except ImportError:
            raise ImportError('You must have networkx installed to export networkx graphs')

        result = Graph()
        for row in self._mst:
            result.add_edge(row[0], row[1], weight=row[2])

        data_dict = {index: tuple(row) for index, row in enumerate(self._data)}
        set_node_attributes(result, 'data', data_dict)

        return result
