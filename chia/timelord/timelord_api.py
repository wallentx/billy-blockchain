from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, ClassVar, Optional, cast

from chia_rs.sized_ints import uint64

from chia.protocols import timelord_protocol
from chia.protocols.timelord_protocol import NewPeakTimelord
from chia.rpc.rpc_server import StateChangedProtocol
from chia.server.api_protocol import ApiMetadata
from chia.timelord.iters_from_block import iters_from_block
from chia.timelord.timelord import Timelord
from chia.timelord.types import Chain, IterationType

log = logging.getLogger(__name__)


class TimelordAPI:
    if TYPE_CHECKING:
        from chia.server.api_protocol import ApiProtocol

        _protocol_check: ClassVar[ApiProtocol] = cast("TimelordAPI", None)

    log: logging.Logger
    timelord: Timelord
    metadata: ClassVar[ApiMetadata] = ApiMetadata()

    def __init__(self, timelord) -> None:
        self.log = logging.getLogger(__name__)
        self.timelord = timelord

    def ready(self) -> bool:
        return True

    def _set_state_changed_callback(self, callback: StateChangedProtocol) -> None:
        self.timelord.state_changed_callback = callback

    @metadata.request()
    async def new_peak_timelord(self, new_peak: NewPeakTimelord) -> None:
        if self.timelord.last_state is None:
            return None
        async with self.timelord.lock:
            if self.timelord.bluebox_mode:
                return None
            self.timelord.max_allowed_inactivity_time = 60

            if self.timelord.last_state.peak is None:
                # no known peak
                log.info("no last known peak, switching to new peak")
                self.timelord.new_peak = new_peak
                self.timelord.state_changed("new_peak", {"height": new_peak.reward_chain_block.height})
                return

            # new peak has equal weight but lower iterations
            if (
                self.timelord.last_state.get_weight() == new_peak.reward_chain_block.weight
                and self.timelord.last_state.peak.reward_chain_block.total_iters
                > new_peak.reward_chain_block.total_iters
            ):
                log.info(
                    "Not skipping peak, has equal weight but lower iterations,"
                    f"current peak:{self.timelord.last_state.total_iters} new peak "
                    f"{new_peak.reward_chain_block.total_iters}"
                    f"current rh: {self.timelord.last_state.peak.reward_chain_block.get_hash()}"
                    f"new peak rh: {new_peak.reward_chain_block.get_hash()}"
                )
                self.timelord.new_peak = new_peak
                self.timelord.state_changed("new_peak", {"height": new_peak.reward_chain_block.height})
                return

            # new peak is heavier
            if self.timelord.last_state.get_weight() < new_peak.reward_chain_block.weight:
                # if there is an unfinished block with less iterations, skip so we dont orphan it
                if (
                    new_peak.reward_chain_block.height == self.timelord.last_state.last_height + 1
                    and self.check_orphaned_unfinished_block(new_peak) is True
                ):
                    log.info("there is an unfinished block that this peak would orphan - skip peak")
                    self.timelord.state_changed("skipping_peak", {"height": new_peak.reward_chain_block.height})
                    return

                log.info(
                    "Not skipping peak, don't have. Maybe we are not the fastest timelord "
                    f"height: {new_peak.reward_chain_block.height} weight:"
                    f"{new_peak.reward_chain_block.weight} rh {new_peak.reward_chain_block.get_hash()}"
                )
                self.timelord.new_peak = new_peak
                self.timelord.state_changed("new_peak", {"height": new_peak.reward_chain_block.height})
                return

            if self.timelord.last_state.peak.reward_chain_block.get_hash() == new_peak.reward_chain_block.get_hash():
                log.info("Skipping peak, already have.")
            else:
                log.info(
                    f"Skipping peak height {new_peak.reward_chain_block.height} "
                    f"weight {new_peak.reward_chain_block.weight}"
                )

            self.timelord.state_changed("skipping_peak", {"height": new_peak.reward_chain_block.height})

    def check_orphaned_unfinished_block(self, new_peak: NewPeakTimelord):
        new_peak_unf_rh = new_peak.reward_chain_block.get_unfinished().get_hash()
        for unf_block in self.timelord.unfinished_blocks:
            if unf_block.reward_chain_block.total_iters <= new_peak.reward_chain_block.total_iters:
                if unf_block.reward_chain_block.get_hash() == new_peak_unf_rh:
                    log.debug("unfinished block is the same as the new peak")
                    continue
                # there is an unfinished block that would be orphaned by this peak
                log.info(f"this peak would orphan unfinished block {unf_block.reward_chain_block.get_hash()}")
                return True
        for unf_block in self.timelord.overflow_blocks:
            if unf_block.reward_chain_block.total_iters <= new_peak.reward_chain_block.total_iters:
                if unf_block.reward_chain_block.get_hash() == new_peak_unf_rh:
                    log.debug("overflow unfinished block is the same as the new peak")
                    continue
                # there is an unfinished block (overflow) that would be orphaned by this peak
                log.info(f"this peak would orphan unfinished overflow block {unf_block.reward_chain_block.get_hash()}")
                return True
        return False

    @metadata.request()
    async def new_unfinished_block_timelord(self, new_unfinished_block: timelord_protocol.NewUnfinishedBlockTimelord):
        if self.timelord.last_state is None:
            return None
        async with self.timelord.lock:
            if self.timelord.bluebox_mode:
                return None
            try:
                sp_iters, ip_iters = iters_from_block(
                    self.timelord.constants,
                    new_unfinished_block.reward_chain_block,
                    self.timelord.last_state.get_sub_slot_iters(),
                    self.timelord.last_state.get_difficulty(),
                    self.timelord.get_height(),
                    self.timelord.last_state.get_last_tx_height(),
                )
            except Exception:
                return None
            last_ip_iters = self.timelord.last_state.get_last_ip()
            if sp_iters > ip_iters:
                self.timelord.overflow_blocks.append(new_unfinished_block)
                log.debug(f"Overflow unfinished block, total {self.timelord.total_unfinished}")
            elif ip_iters > last_ip_iters:
                new_block_iters: Optional[uint64] = self.timelord._can_infuse_unfinished_block(new_unfinished_block)
                if new_block_iters:
                    self.timelord.unfinished_blocks.append(new_unfinished_block)
                    for chain in [Chain.REWARD_CHAIN, Chain.CHALLENGE_CHAIN]:
                        self.timelord.iters_to_submit[chain].append(new_block_iters)
                    if self.timelord.last_state.get_deficit() < self.timelord.constants.MIN_BLOCKS_PER_CHALLENGE_BLOCK:
                        self.timelord.iters_to_submit[Chain.INFUSED_CHALLENGE_CHAIN].append(new_block_iters)
                    self.timelord.iteration_to_proof_type[new_block_iters] = IterationType.INFUSION_POINT
                    self.timelord.total_unfinished += 1
                    log.debug(f"Non-overflow unfinished block, total {self.timelord.total_unfinished}")

    @metadata.request()
    async def request_compact_proof_of_time(self, vdf_info: timelord_protocol.RequestCompactProofOfTime):
        async with self.timelord.lock:
            if not self.timelord.bluebox_mode:
                return None
            now = time.time()
            # work older than 5s can safely be assumed to be from the previous batch, and needs to be cleared
            while self.timelord.pending_bluebox_info and (now - self.timelord.pending_bluebox_info[0][0] > 5):
                del self.timelord.pending_bluebox_info[0]
            self.timelord.pending_bluebox_info.append((now, vdf_info))
