"""The model, which is RelBench's reference architecture rather than ours.

Three pieces, each doing one job:

``HeteroEncoder`` turns each table's TensorFrame into node embeddings, using
a ResNet over the encoded columns. ``HeteroTemporalEncoder`` adds a
relative-time signal, which is what stops a 2019 row and a 2024 row looking
identical to the message passing. ``HeteroGraphSAGE`` does the message
passing itself over the foreign-key edges. A small linear head maps the seed
nodes' embeddings to the task's output.

Using the reference architecture is deliberate. The interesting question here
is what relational deep learning does on this dataset, not whether a
hand-tuned architecture can beat it, and a bespoke model would make the
result impossible to compare against anything.
"""
from __future__ import annotations

import torch
from torch import Tensor
from torch_geometric.data import HeteroData


class Model(torch.nn.Module):
    def __init__(
        self,
        data: HeteroData,
        col_stats_dict: dict,
        out_channels: int,
        channels: int = 128,
        num_layers: int = 2,
        aggr: str = "sum",
    ) -> None:
        super().__init__()
        from relbench.modeling.nn import (
            HeteroEncoder,
            HeteroGraphSAGE,
            HeteroTemporalEncoder,
        )

        self.encoder = HeteroEncoder(
            channels=channels,
            node_to_col_names_dict={
                node_type: data[node_type].tf.col_names_dict
                for node_type in data.node_types
            },
            node_to_col_stats=col_stats_dict,
        )
        # Only tables that carry a timestamp get a temporal encoding. In this
        # graph that is career_metrics and editions; the dimension tables are
        # timeless and would have nothing to encode.
        self.temporal_encoder = HeteroTemporalEncoder(
            node_types=[
                node_type for node_type in data.node_types
                if "time" in data[node_type]
            ],
            channels=channels,
        )
        self.gnn = HeteroGraphSAGE(
            node_types=data.node_types,
            edge_types=data.edge_types,
            channels=channels,
            aggr=aggr,
            num_layers=num_layers,
        )
        self.head = torch.nn.Linear(channels, out_channels)

    def forward(self, batch: HeteroData, entity_table: str) -> Tensor:
        seed_time = batch[entity_table].seed_time
        x_dict = self.encoder(batch.tf_dict)

        rel_time_dict = self.temporal_encoder(
            seed_time, batch.time_dict, batch.batch_dict)
        for node_type, rel_time in rel_time_dict.items():
            x_dict[node_type] = x_dict[node_type] + rel_time

        x_dict = self.gnn(
            x_dict,
            batch.edge_index_dict,
            batch.num_sampled_nodes_dict,
            batch.num_sampled_edges_dict,
        )
        # The seed nodes are the first `batch_size` rows of the entity table
        # in the sampled subgraph. Everything after them is neighbourhood.
        return self.head(x_dict[entity_table][: seed_time.size(0)])
