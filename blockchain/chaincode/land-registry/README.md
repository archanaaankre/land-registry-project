# Land Registry Chaincode (Hyperledger Fabric)

This directory contains the Hyperledger Fabric chaincode for the Land Registry project.

## Architecture

The chaincode is implemented in Go using the `fabric-contract-api-go` package. It provides smart contract functions for managing land parcels and ownership transfers on a permissioned Fabric network.

## Data Structures

### Parcel
Stored on the ledger with key = `parcel_id`.

| Field | Type | Description |
|-------|------|-------------|
| docType | string | Always "PARCEL" |
| parcelId | string | Unique parcel identifier |
| cadastralNumber | string | Cadastral number |
| location | string | Location description |
| area | float64 | Area value |
| areaUnit | string | Unit of area (SQ_METERS, HECTARES, ACRES) |
| status | string | Parcel status (ACTIVE, INACTIVE, DISPUTED) |
| ownerId | string | Current owner user ID |
| createdAt | string | RFC3339 timestamp |
| updatedAt | string | RFC3339 timestamp |
| blockchainTxId | string | Fabric transaction ID |
| createdBy | string | Creator identity |

### TransferRequest
Stored on the ledger with key = `request_id`.

| Field | Type | Description |
|-------|------|-------------|
| docType | string | Always "TRANSFER" |
| requestId | string | Unique transfer request identifier |
| parcelId | string | Parcel being transferred |
| sellerId | string | Current owner |
| buyerId | string | Buyer user ID |
| buyerReference | string | Original buyer reference |
| status | string | SUBMITTED, APPROVED, COMPLETED |
| submittedAt | string | RFC3339 timestamp |
| updatedAt | string | RFC3339 timestamp |
| blockchainTxId | string | Fabric transaction ID |
| reviewReason | string | Review reason |
| reviewedAt | string | RFC3339 timestamp |
| reviewerId | string | Reviewer identity |

## Transaction Functions

### RegisterParcel

Registers a new parcel on the ledger.

**Arguments:** `[parcel_id, cadastral_number, location, area, area_unit, owner_id]`

**Returns:** Fabric transaction ID

**Authorization:** Any authenticated Fabric identity (registrar)

**Preconditions:**
- Parcel ID must not already exist
- All fields must be non-empty

**Ledger effect:** Creates a `PARCEL` key-value pair

### SubmitTransfer

Creates a transfer request on the ledger.

**Arguments:** `[request_id, parcel_id, seller_id, buyer_id]`

**Returns:** Fabric transaction ID

**Authorization:** Any authenticated Fabric identity (registrar)

**Preconditions:**
- Parcel must exist
- Seller must be the current owner of the parcel
- Transfer request ID must not already exist

**Ledger effect:** Creates a `TRANSFER` key-value pair with status `SUBMITTED`

### ApproveTransfer

Approves a transfer request on the ledger.

**Arguments:** `[request_id]`

**Returns:** Fabric transaction ID

**Authorization:** Any authenticated Fabric identity (registrar)

**Preconditions:**
- Transfer request must exist
- Transfer status must be `SUBMITTED`

**Ledger effect:** Updates transfer status to `APPROVED`

### ConfirmTransfer

Confirms a transfer on the ledger and updates parcel ownership.

**Arguments:** `[request_id, tx_id]`

**Returns:** Fabric transaction ID

**Authorization:** Any authenticated Fabric identity (registrar)

**Preconditions:**
- Transfer request must exist
- Transfer status must be `APPROVED`

**Ledger effect:**
- Updates transfer status to `COMPLETED` and sets `blockchainTxId`
- Updates parcel owner to the buyer and sets `blockchainTxId`

### GetParcel

Retrieves a parcel record from the ledger.

**Arguments:** `[parcel_id]`

**Returns:** Parcel JSON object

### GetTransfer

Retrieves a transfer request from the ledger.

**Arguments:** `[request_id]`

**Returns:** TransferRequest JSON object

### GetParcelHistory

Retrieves all transfer events for a parcel from the ledger.

**Arguments:** `[parcel_id]`

**Returns:** Array of TransferRequest JSON objects

### VerifyTransaction

Verifies a transfer transaction on the ledger.

**Arguments:** `[request_id]`

**Returns:** TransferRequest JSON object (same as GetTransfer)

### QueryParcelsByOwner

Retrieves all parcels owned by a given owner.

**Arguments:** `[owner_id]`

**Returns:** Array of Parcel JSON objects

## Gateway Compatibility

The chaincode functions match the interface documented in `backend/app/transfers/fabric_gateway.py`:

| Gateway Method | Chaincode Function | Arguments |
|----------------|-------------------|-----------|
| `_submit_transfer` | `SubmitTransfer` | [request_id, parcel_id, seller_id, buyer_id] |
| `_query_transfer` | `GetTransfer` | [request_id] |

The gateway expects:
- `submit()` → calls `SubmitTransfer`, returns transaction ID
- `verify_confirmation()` → calls `GetTransfer`, checks status is `COMPLETED`

## Go Dependencies

| Module | Version | Purpose |
|--------|---------|---------|
| github.com/hyperledger/fabric-contract-api-go | v2.5.0+incompatible | Chaincode API framework |
| github.com/stretchr/testify | v1.9.0 | Test assertions |

## Build Instructions

```bash
cd blockchain/chaincode/land-registry
go mod tidy
go build ./...
```

## Test Instructions

```bash
cd blockchain/chaincode/land-registry
go test ./... -v
```

Tests use `fabric-contract-api-go/mock` stub and do not require a running Fabric network.

## Chaincode Deployment Instructions

1. Package the chaincode:
   ```bash
   peer lifecycle chaincode package land-registry.tar.gz --lang golang --path land-registry --label land-registry_1
   ```

2. Install the chaincode on each peer:
   ```bash
   peer lifecycle chaincode install land-registry.tar.gz
   ```

3. Approve the chaincode for your organization:
   ```bash
   peer lifecycle chaincode approveformyorg -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --channelID mychannel --name land-registry --version 1 --package-id <package-id> --sequence 1 --tls --cafile <orderer-tls-ca>
   ```

4. Commit the chaincode definition:
   ```bash
   peer lifecycle chaincode commit -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --channelID mychannel --name land-registry --version 1 --sequence 1 --tls --cafile <orderer-tls-ca> --peerAddresses localhost:7051 --tlsRootCertFiles <peer-tls-ca>
   ```

5. Initialize the chaincode (optional, InitLedger is a no-op):
   ```bash
   peer chaincode invoke -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile <orderer-tls-ca> -C mychannel -n land-registry -c '{"function":"InitLedger","Args":[]}'
   ```

## Compatibility with fabric_gateway.py

The Python gateway in `backend/app/transfers/fabric_gateway.py` expects:

| Gateway Method | Chaincode Function | Arguments |
|----------------|-------------------|-----------|
| `_submit_transfer` | `SubmitTransfer` | [request_id, parcel_id, seller_id, buyer_id] |
| `_query_transfer` | `GetTransfer` | [request_id] |

The gateway returns:
- `submit()`: `BlockchainSubmission(status=SUBMITTED, tx_id=<fabric_tx_id>)`
- `verify_confirmation()`: `BlockchainConfirmation(status=CONFIRMED, verified=True, tx_id=<...>)` when transfer status is `COMPLETED`

## Security Considerations

- All chaincode functions validate their arguments
- Duplicate parcel registration is prevented
- Transfer submission verifies the seller is the current parcel owner
- Transfer confirmation verifies the transfer is in `APPROVED` state
- No confidential personal information or document contents are stored on-chain
- Document hashes are stored in a separate `document_hashes` table in the PostgreSQL database, not on the Fabric ledger
