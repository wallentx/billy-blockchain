from __future__ import annotations

import logging
import random

import pytest
from chia_rs import BlockRecord, UnfinishedBlock
from chia_rs.sized_ints import uint64

from chia._tests.connection_utils import add_dummy_connection
from chia._tests.core.full_node.stores.test_coin_store import get_future_reward_coins
from chia._tests.core.node_height import node_height_at_least
from chia._tests.util.misc import BenchmarkRunner
from chia._tests.util.time_out_assert import time_out_assert
from chia.consensus.pot_iterations import is_overflow_block
from chia.protocols import full_node_protocol as fnp
from chia.types.condition_opcodes import ConditionOpcode
from chia.types.condition_with_args import ConditionWithArgs
from chia.util.casts import int_to_bytes

log = logging.getLogger(__name__)


class TestPerformance:
    @pytest.mark.anyio
    async def test_full_block_performance(
        self, request: pytest.FixtureRequest, wallet_nodes_perf, self_hostname, benchmark_runner: BenchmarkRunner
    ):
        full_node_1, server_1, wallet_a, wallet_receiver, bt = wallet_nodes_perf
        blocks = await full_node_1.get_all_full_blocks()
        full_node_1.full_node.mempool_manager.limit_factor = 1

        wallet_ph = wallet_a.get_new_puzzlehash()
        blocks = bt.get_consecutive_blocks(
            10,
            block_list_input=blocks,
            guarantee_transaction_block=True,
            farmer_reward_puzzle_hash=wallet_ph,
            pool_reward_puzzle_hash=wallet_ph,
        )
        for block in blocks:
            await full_node_1.full_node.add_block(block)

        start_height = (
            full_node_1.full_node.blockchain.get_peak().height
            if full_node_1.full_node.blockchain.get_peak() is not None
            else -1
        )
        _incoming_queue, node_id = await add_dummy_connection(server_1, self_hostname, 12312)
        fake_peer = server_1.all_connections[node_id]
        # Mempool has capacity of 100, make 110 unspents that we can use
        puzzle_hashes = []

        # Makes a bunch of coins
        for i in range(20):
            conditions_dict: dict = {ConditionOpcode.CREATE_COIN: []}
            # This should fit in one transaction
            for _ in range(100):
                receiver_puzzlehash = wallet_receiver.get_new_puzzlehash()
                puzzle_hashes.append(receiver_puzzlehash)
                output = ConditionWithArgs(ConditionOpcode.CREATE_COIN, [receiver_puzzlehash, int_to_bytes(100000000)])

                conditions_dict[ConditionOpcode.CREATE_COIN].append(output)

            spend_bundle = wallet_a.generate_signed_transaction(
                100,
                puzzle_hashes[0],
                get_future_reward_coins(blocks[1 + i])[0],
                condition_dic=conditions_dict,
            )
            assert spend_bundle is not None

            respond_transaction_2 = fnp.RespondTransaction(spend_bundle)
            await full_node_1.respond_transaction(respond_transaction_2, fake_peer)

            blocks = bt.get_consecutive_blocks(
                1,
                block_list_input=blocks,
                guarantee_transaction_block=True,
                transaction_data=spend_bundle,
            )
            await full_node_1.full_node.add_block(blocks[-1], fake_peer)

        await time_out_assert(20, node_height_at_least, True, full_node_1, start_height + 20)

        spend_bundles = []
        spend_bundle_ids = []

        # Fill mempool
        for puzzle_hash in puzzle_hashes[1:]:
            coin_record = (await full_node_1.full_node.coin_store.get_coin_records_by_puzzle_hash(True, puzzle_hash))[0]
            receiver_puzzlehash = wallet_receiver.get_new_puzzlehash()
            if puzzle_hash == puzzle_hashes[-1]:
                fee = 100000000  # 100 million (20 fee per cost)
            else:
                fee = random.randint(1, 100000000)
            spend_bundle = wallet_receiver.generate_signed_transaction(
                uint64(500), receiver_puzzlehash, coin_record.coin, fee=fee
            )
            spend_bundles.append(spend_bundle)
            spend_bundle_ids.append(spend_bundle.get_hash())

        with benchmark_runner.assert_runtime(seconds=0.0055, label="mempool"):
            num_tx: int = 0
            for spend_bundle, spend_bundle_id in zip(spend_bundles, spend_bundle_ids):
                num_tx += 1
                respond_transaction = fnp.RespondTransaction(spend_bundle)

                await full_node_1.respond_transaction(respond_transaction, fake_peer)

                request_transaction = fnp.RequestTransaction(spend_bundle_id)
                req = await full_node_1.request_transaction(request_transaction)

                if req is None:
                    break

        log.warning(f"Num Tx: {num_tx}")

        # Create an unfinished block
        peak = full_node_1.full_node.blockchain.get_peak()
        assert peak is not None
        curr: BlockRecord = peak
        while not curr.is_transaction_block:
            curr = full_node_1.full_node.blockchain.block_record(curr.prev_hash)
        mempool_bundle = full_node_1.full_node.mempool_manager.create_bundle_from_mempool(curr.header_hash)
        if mempool_bundle is None:
            spend_bundle = None
        else:
            spend_bundle = mempool_bundle[0]

        current_blocks = await full_node_1.get_all_full_blocks()
        blocks = bt.get_consecutive_blocks(
            1,
            transaction_data=spend_bundle,
            block_list_input=current_blocks,
            guarantee_transaction_block=True,
        )
        block = blocks[-1]
        if is_overflow_block(bt.constants, block.reward_chain_block.signage_point_index):
            sub_slots = block.finished_sub_slots[:-1]
        else:
            sub_slots = block.finished_sub_slots
        unfinished = UnfinishedBlock(
            sub_slots,
            block.reward_chain_block.get_unfinished(),
            block.challenge_chain_sp_proof,
            block.reward_chain_sp_proof,
            block.foliage,
            block.foliage_transaction_block,
            block.transactions_info,
            block.transactions_generator,
            [],
        )

        with benchmark_runner.assert_runtime(seconds=0.1, label="unfinished"):
            res = await full_node_1.respond_unfinished_block(fnp.RespondUnfinishedBlock(unfinished), fake_peer)

        log.warning(f"Res: {res}")

        with benchmark_runner.assert_runtime(seconds=0.1, label="full block"):
            # No transactions generator, the full node already cached it from the unfinished block
            block_small = block.replace(transactions_generator=None)
            res = await full_node_1.full_node.add_block(block_small)

        log.warning(f"Res: {res}")
