# Teku Light Client Protocol

Implementing server-side light client protocol in Teku consensus client for resource-constrained nodes.

## Motivation

The Altair upgrade introduced the [light client sync protocol](https://github.com/ethereum/consensus-specs/blob/master/specs/altair/light-client/), which allows resource-constrained nodes to track Ethereum's state without replaying the full consensus chain. Instead of trusting a centralized provider, a light client can verify compact proofs and aggregated signatures from rotating sync committees, making it possible for low-resource infrastructure to follow Ethereum.

In this protocol, full beacon nodes need to act as reliable data providers. They must produce, keep, and share the light client data that enables other peers to bootstrap, follow finalized checkpoints, and track the latest head. This is important for environments where running a full node is unrealistic but relying entirely on centralized infrastructure weakens Ethereum's trust model.

## Project description

Teku already supports the initial light client bootstrap flow, which gives a light client a trusted starting point. However, bootstrap data alone is not enough. After a light client starts, it also needs fresh updates so it can keep following Ethereum over time.

The goal of this project is to complete Teku's server-side light client support so Teku can generate, store, and serve regular light client updates, finality updates, and optimistic updates through the standard network and API channels.

The project is server-side only and covers REST, gossip, and request/response networking across active forks from Altair onward. Client-side light client sync, where Teku would act as a light client itself, is out of scope.

## Specification

The implementation includes several components:

**1. SSZ Containers**
Existing (reuse):
* `LightClientHeader`: Beacon block header with execution payload header (post-Capella) and Merkle proof branches.
* `LightClientBootstrap`: Contains `header`, `current_sync_committee`, and `current_sync_committee_branch`.
* `LightClientUpdate`: Exists but schema is not fork-aware for Electra gindices.

New:
* `LightClientFinalityUpdate`: Contains `attested_header`, `finalized_header`, `finality_branch`, `sync_aggregate`, and `signature_slot`.
* `LightClientOptimisticUpdate`: Contains `attested_header`, `sync_aggregate`, and `signature_slot`.
* `LightClientUpdateSchemaElectra` / `LightClientFinalityUpdateSchemaElectra`: Fork-aware schema variants using Electra gindices (`FINALIZED_ROOT_GINDEX_ELECTRA=169`, `NEXT_SYNC_COMMITTEE_GINDEX_ELECTRA=87`).

**2. Server-Side Data Generation**
Existing (reuse):
* `getLightClientBootstrap`: Generates bootstrap from beacon state.
* `BeaconStateAltair.createCurrentSyncCommitteeProof()`: Computes the current sync committee Merkle branch.
* `MerkleUtil.constructMerkleProof(root, leafGeneralizedIndex)`: Generic Merkle proof builder.

New:
* `createNextSyncCommitteeProof()`: Proof helper on `BeaconStateAltair` for the next sync committee branch.
* `createFinalityBranchProof()`: Proof helper computing the finality branch (leaf is `finalized_checkpoint.root`, two levels deep via `getChildGeneralizedIndex`).
* `create_light_client_update(attestedBlock, attestedState, finalizedBlock)`: Generates a `LightClientUpdate` at sync committee period boundaries.
* `create_light_client_finality_update(update)`: Derives a `LightClientFinalityUpdate` from an update whenever a new block is finalized.
* `create_light_client_optimistic_update(update)`: Derives a `LightClientOptimisticUpdate` on every new head block using the `sync_aggregate` from the attesting block.
* `is_better_update(newUpdate, oldUpdate)`: Predicate implementing the spec's best-update comparison logic (supermajority → finality+committee → participation → attested slot → older signature slot).

**3. Storage & Collection**
* `LightClientUpdateStore`: In-memory cache using `ConcurrentSkipListMap<period, LightClientUpdate>` + volatile latest finality/optimistic updates. Queries: `getBestUpdatesInRange(startPeriod, count)`, `getLatestFinalityUpdate()`, `getLatestOptimisticUpdate()`.
* `LightClientServerService`: Subscribes to block-import and finalization event channels. For each imported block with a sync aggregate, loads the attested block/state via `RecentChainData`, calls the `create_*` methods, and offers results to the store off the import hot path.
* `computeSyncCommitteePeriod(epoch)`: Helper (`epoch // EPOCHS_PER_SYNC_COMMITTEE_PERIOD`).
* Reorg Handling: Logic to invalidate and regenerate stored light client data when chain reorganizations occur.

**4. REST API Endpoints**
Existing (fix):
* `GET /eth/v1/beacon/light_client/bootstrap/{block_root}`: Already implemented.
* `GetLightClientUpdatesByRange`: Currently returns **501 Not Implemented** — needs completion.

New:
* `GET /eth/v1/beacon/light_client/updates?start_period={}&count={}`: Returns `LightClientUpdate` objects for the requested sync committee period range.
* `GET /eth/v1/beacon/light_client/finality_update`: Returns the latest `LightClientFinalityUpdate`.
* `GET /eth/v1/beacon/light_client/optimistic_update`: Returns the latest `LightClientOptimisticUpdate`.
* `ChainDataProvider`: New methods `getLightClientUpdatesByRange`, `getLightClientFinalityUpdate`, `getLightClientOptimisticUpdate` backed by the store.
* All endpoints support both JSON and SSZ (`application/octet-stream`) response formats via the `Accept` header, with fork `version` in response metadata.

**5. P2P Networking & Gossip**
* Gossip Topic (`/eth2/<fork_digest>/light_client_finality_update/ssz_snappy`): Publishes `LightClientFinalityUpdate` objects when a new finalized checkpoint is reached.
* Gossip Topic (`/eth2/<fork_digest>/light_client_optimistic_update/ssz_snappy`): Publishes `LightClientOptimisticUpdate` objects on every new head.
* `GossipTopicName`: Add `LIGHT_CLIENT_FINALITY_UPDATE` and `LIGHT_CLIENT_OPTIMISTIC_UPDATE` entries.
* Gossip managers extending `AbstractGossipManager`, registered in `GossipForkSubscriptionsAltair.addGossipManagers`.
* Req/Resp RPC methods registered in `BeaconChainMethods`:
  * `light_client_bootstrap` (req = block root, single response)
  * `light_client_updates_by_range` (streamed response, needs `LightClientUpdatesByRangeRequestMessage`)
  * `light_client_finality_update` (empty request, single response)
  * `light_client_optimistic_update` (empty request, single response)

## Roadmap

| Phase | Timeline | Focus | Expected outcome |
|-------|----------|-------|------------------|
| 1 | Weeks 6-8 | Spec layer and generation | Add the missing update types, fork-aware schema support, proof helpers, update generation, fixtures, and reference tests. |
| 2 | Weeks 9-11 | In-memory store | Build the update store, best-update selection logic, and unit tests for replacement and range queries. |
| 3 | Weeks 11-13 | Runtime collection | Connect the store to block import and finalization events while keeping update generation off the import hot path. |
| 4 | Weeks 14-15 | REST API support | Complete ranged updates, finality update, and optimistic update endpoints with JSON and SSZ integration tests. |
| 5 | Weeks 16-18 | Gossip publishing | Publish finality and optimistic updates to the P2P network when new data becomes available. |
| 6 | Weeks 19-20 | Request/response networking | Add peer request handlers for bootstrap data and light client updates, with round-trip networking tests. |

## Possible challenges

* Historical data may not always be available on pruned or minimal nodes, so I need to figure out the workarounds.
* Fork-specific proof details differ across protocol versions, so tests need to cover both earlier forks and newer fork layouts.
* Choosing the best update for a period has subtle ordering rules and should be tested independently.

## Goal of the project

Success looks like:
* Teku beacon nodes serve all four light client REST API endpoints with correct, spec-compliant data.
* Teku gossips `LightClientFinalityUpdate` and `LightClientOptimisticUpdate` to the P2P network.
* Teku responds to `LightClientBootstrapByRoot` and `LightClientUpdatesByRange` req/resp queries.
* Implementation passes all relevant consensus-spec-tests and interoperates with light clients syncing from other beacon node implementations.
* Unit, reference, REST integration, and networking tests cover update generation, proof helpers, store behavior, endpoints, gossip publishing, and request/response round trips.

## Collaborators

### Fellows 

* **Abhivansh** ([@akronim26](https://github.com/akronim26))

### Mentors


## Resources

* [Light Client Sync Protocol Spec](https://github.com/ethereum/consensus-specs/blob/master/specs/global/light-client/sync-protocol.md)
* [Light Client Full Node Spec](https://github.com/ethereum/consensus-specs/blob/master/specs/global/light-client/full-node.md)
* [Light Client P2P Networking Spec](https://github.com/ethereum/consensus-specs/blob/master/specs/global/light-client/p2p-interface.md)
* [Beacon REST API - Light Client Endpoints](https://ethereum.github.io/beacon-APIs/#/Beacon/getLightClientBootstrap)
* [Teku Consensus Client Repository](https://github.com/Consensys/teku)
* [Teku Issue #6287 - Light Client Sync Endpoints](https://github.com/Consensys/teku/issues/6287)
* [Teku Pull Request #6384 - Partial implementation of Light Client Protocol](https://github.com/Consensys/teku/pull/6384)
