from __future__ import annotations

import dataclasses
import sys
from collections.abc import Sequence
from typing import Optional

from chia_rs.sized_bytes import bytes32
from chia_rs.sized_ints import uint16, uint32, uint64

from chia.cmds.cmd_helpers import WalletClientInfo
from chia.cmds.cmds_util import CMDCoinSelectionConfigLoader, CMDTXConfigLoader, cli_confirm
from chia.cmds.param_types import CliAmount
from chia.cmds.wallet_funcs import get_mojo_per_unit, get_wallet_type, print_balance
from chia.types.blockchain_format.coin import Coin
from chia.util.bech32m import encode_puzzle_hash
from chia.util.config import selected_network_address_prefix
from chia.wallet.conditions import ConditionValidTimes
from chia.wallet.transaction_record import TransactionRecord
from chia.wallet.util.wallet_types import WalletType
from chia.wallet.wallet_request_types import CombineCoins, SplitCoins


async def async_list(
    *,
    client_info: WalletClientInfo,
    wallet_id: int,
    max_coin_amount: CliAmount,
    min_coin_amount: CliAmount,
    excluded_amounts: Sequence[CliAmount],
    excluded_coin_ids: Sequence[bytes32],
    show_unconfirmed: bool,
    paginate: Optional[bool],
) -> None:
    addr_prefix = selected_network_address_prefix(client_info.config)
    if paginate is None:
        paginate = sys.stdout.isatty()
    try:
        wallet_type = await get_wallet_type(wallet_id=wallet_id, wallet_client=client_info.client)
        mojo_per_unit = get_mojo_per_unit(wallet_type)
    except LookupError:
        print(f"Wallet id: {wallet_id} not found.")
        return
    if not (await client_info.client.get_sync_status()).synced:
        print("Wallet not synced. Please wait.")
        return
    conf_coins, unconfirmed_removals, unconfirmed_additions = await client_info.client.get_spendable_coins(
        wallet_id=wallet_id,
        coin_selection_config=CMDCoinSelectionConfigLoader(
            max_coin_amount=max_coin_amount,
            min_coin_amount=min_coin_amount,
            excluded_coin_amounts=list(excluded_amounts),
            excluded_coin_ids=list(excluded_coin_ids),
        ).to_coin_selection_config(mojo_per_unit),
    )
    print(f"There are a total of {len(conf_coins) + len(unconfirmed_additions)} coins in wallet {wallet_id}.")
    print(f"{len(conf_coins)} confirmed coins.")
    print(f"{len(unconfirmed_additions)} unconfirmed additions.")
    print(f"{len(unconfirmed_removals)} unconfirmed removals.")
    print("Confirmed coins:")
    print_coins(
        "\tAddress: {} Amount: {}, Confirmed in block: {}\n",
        [(cr.coin, str(cr.confirmed_block_index)) for cr in conf_coins],
        mojo_per_unit,
        addr_prefix,
        paginate,
    )
    if show_unconfirmed:
        print("\nUnconfirmed Removals:")
        print_coins(
            "\tPrevious Address: {} Amount: {}, Confirmed in block: {}\n",
            [(cr.coin, str(cr.confirmed_block_index)) for cr in unconfirmed_removals],
            mojo_per_unit,
            addr_prefix,
            paginate,
        )
        print("\nUnconfirmed Additions:")
        print_coins(
            "\tNew Address: {} Amount: {}, Not yet confirmed in a block.{}\n",
            [(coin, "") for coin in unconfirmed_additions],
            mojo_per_unit,
            addr_prefix,
            paginate,
        )


def print_coins(
    target_string: str, coins: list[tuple[Coin, str]], mojo_per_unit: int, addr_prefix: str, paginate: bool
) -> None:
    if len(coins) == 0:
        print("\tNo Coins.")
        return
    num_per_screen = 5 if paginate else len(coins)
    for i in range(0, len(coins), num_per_screen):
        for j in range(num_per_screen):
            if i + j >= len(coins):
                break
            coin, conf_height = coins[i + j]
            address = encode_puzzle_hash(coin.puzzle_hash, addr_prefix)
            amount_str = print_balance(coin.amount, mojo_per_unit, "", decimal_only=True)
            print(f"Coin ID: 0x{coin.name().hex()}")
            print(target_string.format(address, amount_str, conf_height))

        if i + num_per_screen >= len(coins):
            return None
        print("Press q to quit, or c to continue")
        while True:
            entered_key = sys.stdin.read(1)
            if entered_key.lower() == "q":
                return None
            elif entered_key.lower() == "c":
                break


async def async_combine(
    *,
    client_info: WalletClientInfo,
    wallet_id: int,
    fee: uint64,
    max_coin_amount: CliAmount,
    min_coin_amount: CliAmount,
    excluded_amounts: Sequence[CliAmount],
    coins_to_exclude: Sequence[bytes32],
    reuse_puzhash: Optional[bool],
    number_of_coins: int,
    target_coin_amount: Optional[CliAmount],
    target_coin_ids: Sequence[bytes32],
    largest_first: bool,
    push: bool,
    condition_valid_times: ConditionValidTimes,
    override: bool,
) -> list[TransactionRecord]:
    try:
        wallet_type = await get_wallet_type(wallet_id=wallet_id, wallet_client=client_info.client)
        mojo_per_unit = get_mojo_per_unit(wallet_type)
    except LookupError:
        print(f"Wallet id: {wallet_id} not found.")
        return []
    if not (await client_info.client.get_sync_status()).synced:
        print("Wallet not synced. Please wait.")
        return []

    tx_config = CMDTXConfigLoader(
        max_coin_amount=max_coin_amount,
        min_coin_amount=min_coin_amount,
        excluded_coin_amounts=list(excluded_amounts),
        excluded_coin_ids=list(coins_to_exclude),
        reuse_puzhash=reuse_puzhash,
    ).to_tx_config(mojo_per_unit, client_info.config, client_info.fingerprint)

    final_target_coin_amount = None if target_coin_amount is None else target_coin_amount.convert_amount(mojo_per_unit)

    combine_request = CombineCoins(
        wallet_id=uint32(wallet_id),
        target_coin_amount=final_target_coin_amount,
        number_of_coins=uint16(number_of_coins),
        target_coin_ids=list(target_coin_ids),
        largest_first=largest_first,
        fee=fee,
        push=False,
    )
    resp = await client_info.client.combine_coins(
        combine_request,
        tx_config,
        timelock_info=condition_valid_times,
    )

    if not override and wallet_id == 1 and fee >= sum(coin.amount for tx in resp.transactions for coin in tx.removals):
        print("Fee is >= the amount of coins selected. To continue, please use --override flag.")
        return []

    print(f"Transactions would combine up to {number_of_coins} coins.")
    if push:
        cli_confirm("Would you like to Continue? (y/n): ")
        resp = await client_info.client.combine_coins(
            dataclasses.replace(combine_request, push=True),
            tx_config,
            timelock_info=condition_valid_times,
        )
        for tx in resp.transactions:
            print(f"Transaction sent: {tx.name}")
            print(
                f"To get status, use command: chia wallet get_transaction -f {client_info.fingerprint} -tx 0x{tx.name}"
            )

    return resp.transactions


async def async_split(
    *,
    client_info: WalletClientInfo,
    wallet_id: int,
    fee: uint64,
    number_of_coins: Optional[int],
    amount_per_coin: Optional[CliAmount],
    target_coin_id: bytes32,
    max_coin_amount: CliAmount,
    min_coin_amount: CliAmount,
    excluded_amounts: Sequence[CliAmount],
    coins_to_exclude: Sequence[bytes32],
    reuse_puzhash: Optional[bool],
    push: bool,
    condition_valid_times: ConditionValidTimes,
) -> list[TransactionRecord]:
    try:
        wallet_type = await get_wallet_type(wallet_id=wallet_id, wallet_client=client_info.client)
        mojo_per_unit = get_mojo_per_unit(wallet_type)
    except LookupError:
        print(f"Wallet id: {wallet_id} not found.")
        return []
    if not (await client_info.client.get_sync_status()).synced:
        print("Wallet not synced. Please wait.")
        return []

    if number_of_coins is None and amount_per_coin is None:
        print("Must use either -a or -n. For more information run --help.")
        return []

    if number_of_coins is None:
        coins = await client_info.client.get_coin_records_by_names([target_coin_id])
        if len(coins) == 0:
            print("Could not find target coin.")
            return []
        assert amount_per_coin is not None
        number_of_coins = int(coins[0].coin.amount // amount_per_coin.convert_amount(mojo_per_unit))
    elif amount_per_coin is None:
        coins = await client_info.client.get_coin_records_by_names([target_coin_id])
        if len(coins) == 0:
            print("Could not find target coin.")
            return []
        assert number_of_coins is not None
        amount_per_coin = CliAmount(True, uint64(coins[0].coin.amount // number_of_coins))

    final_amount_per_coin = amount_per_coin.convert_amount(mojo_per_unit)

    tx_config = CMDTXConfigLoader(
        max_coin_amount=max_coin_amount,
        min_coin_amount=min_coin_amount,
        excluded_coin_amounts=list(excluded_amounts),
        excluded_coin_ids=list(coins_to_exclude),
        reuse_puzhash=reuse_puzhash,
    ).to_tx_config(mojo_per_unit, client_info.config, client_info.fingerprint)

    transactions: list[TransactionRecord] = (
        await client_info.client.split_coins(
            SplitCoins(
                wallet_id=uint32(wallet_id),
                number_of_coins=uint16(number_of_coins),
                amount_per_coin=uint64(final_amount_per_coin),
                target_coin_id=target_coin_id,
                fee=fee,
                push=push,
            ),
            tx_config=tx_config,
            timelock_info=condition_valid_times,
        )
    ).transactions

    if push:
        for tx in transactions:
            print(f"Transaction sent: {tx.name}")
            print(
                f"To get status, use command: chia wallet get_transaction -f {client_info.fingerprint} -tx 0x{tx.name}"
            )
    dust_threshold = client_info.config.get("xch_spam_amount", 1000000)  # min amount per coin in mojo
    spam_filter_after_n_txs = client_info.config.get(
        "spam_filter_after_n_txs", 200
    )  # how many txs to wait before filtering
    if final_amount_per_coin < dust_threshold and wallet_type == WalletType.STANDARD_WALLET:
        print(
            f"WARNING: The amount per coin: {amount_per_coin.amount} is less than the dust threshold: "
            f"{dust_threshold / (1 if amount_per_coin.mojos else mojo_per_unit)}. Some or all of the Coins "
            f"{'will' if number_of_coins > spam_filter_after_n_txs else 'may'} not show up in your wallet unless "
            f"you decrease the dust limit to below {final_amount_per_coin} mojos or disable it by setting it to 0."
        )
    return transactions
