package chaincode

import (
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// LandRegistryChaincode implements the smart contract for land registry operations.
type LandRegistryChaincode struct {
	contractapi.Contract
}

// Parcel represents a land parcel stored on the ledger.
type Parcel struct {
	DocType         string  `json:"docType"`
	ParcelID        string  `json:"parcelId"`
	CadastralNumber string  `json:"cadastralNumber"`
	Location        string  `json:"location"`
	Area            float64 `json:"area"`
	AreaUnit        string  `json:"areaUnit"`
	Status          string  `json:"status"`
	OwnerID         string  `json:"ownerId"`
	CreatedAt       string  `json:"createdAt"`
	UpdatedAt       string  `json:"updatedAt"`
	BlockchainTxID  string  `json:"blockchainTxId"`
	CreatedBy       string  `json:"createdBy"`
}

// TransferRequest represents a transfer request stored on the ledger.
type TransferRequest struct {
	DocType         string `json:"docType"`
	RequestID       string `json:"requestId"`
	ParcelID        string `json:"parcelId"`
	SellerID        string `json:"sellerId"`
	BuyerID         string `json:"buyerId"`
	BuyerReference  string `json:"buyerReference"`
	Status          string `json:"status"`
	SubmittedAt     string `json:"submittedAt"`
	UpdatedAt       string `json:"updatedAt"`
	BlockchainTxID  string `json:"blockchainTxId"`
	ReviewReason    string `json:"reviewReason"`
	ReviewedAt      string `json:"reviewedAt"`
	ReviewerID      string `json:"reviewerId"`
}

// InitLedger initializes the chaincode with no data.
func (lc *LandRegistryChaincode) InitLedger(ctx contractapi.TransactionContextInterface) error {
	return nil
}

// RegisterParcel registers a new parcel on the ledger.
// Arguments: parcel_id, cadastral_number, location, area, area_unit, owner_id
func (lc *LandRegistryChaincode) RegisterParcel(ctx contractapi.TransactionContextInterface,
	parcelID, cadastralNumber, location, area, areaUnit, ownerID string) (string, error) {

	if parcelID == "" || cadastralNumber == "" || location == "" ||
		area == "" || areaUnit == "" || ownerID == "" {
		return "", fmt.Errorf("all fields are required for RegisterParcel")
	}

	parsedArea, err := strconv.ParseFloat(area, 64)
	if err != nil {
		return "", fmt.Errorf("area must be a number, got %q", area)
	}
	if parsedArea <= 0 {
		return "", fmt.Errorf("area must be greater than zero, got %v", parsedArea)
	}
	if areaUnit != "SQ_METERS" && areaUnit != "HECTARES" && areaUnit != "ACRES" {
		return "", fmt.Errorf("area_unit must be SQ_METERS, HECTARES or ACRES, got %q", areaUnit)
	}

	existing, err := ctx.GetStub().GetState(parcelID)
	if err != nil {
		return "", fmt.Errorf("failed to read parcel %s: %v", parcelID, err)
	}
	if existing != nil {
		return "", fmt.Errorf("parcel %s already exists", parcelID)
	}

	txID := ctx.GetStub().GetTxID()
	now := time.Now().UTC().Format(time.RFC3339)

	parcel := Parcel{
		DocType:         "PARCEL",
		ParcelID:        parcelID,
		CadastralNumber: cadastralNumber,
		Location:        location,
		Area:            parsedArea,
		AreaUnit:        areaUnit,
		Status:          "ACTIVE",
		OwnerID:         ownerID,
		CreatedAt:       now,
		UpdatedAt:       now,
		BlockchainTxID:  txID,
		CreatedBy:       ctx.GetClientIdentity().GetID(),
	}

	parcelJSON, err := json.Marshal(parcel)
	if err != nil {
		return "", fmt.Errorf("failed to marshal parcel: %v", err)
	}
	if err := ctx.GetStub().PutState(parcelID, parcelJSON); err != nil {
		return "", fmt.Errorf("failed to put parcel state: %v", err)
	}

	// Write a composite-key index entry for parcel lookup by owner/cadastral.
	indexKey, err := ctx.GetStub().CreateCompositeKey("PARCEL", []string{ownerID, parcelID})
	if err != nil {
		return "", fmt.Errorf("failed to create composite key: %v", err)
	}
	if err := ctx.GetStub().PutState(indexKey, []byte{1}); err != nil {
		return "", fmt.Errorf("failed to put index key: %v", err)
	}

	return txID, nil
}

// SubmitTransfer records a new transfer request on the ledger.
// Arguments: request_id, parcel_id, seller_id, buyer_id
func (lc *LandRegistryChaincode) SubmitTransfer(ctx contractapi.TransactionContextInterface,
	requestID, parcelID, sellerID, buyerID string) (string, error) {

	if requestID == "" || parcelID == "" || sellerID == "" || buyerID == "" {
		return "", fmt.Errorf("all fields are required for SubmitTransfer")
	}
	if sellerID == buyerID {
		return "", fmt.Errorf("seller and buyer must be different")
	}

	parcelJSON, err := ctx.GetStub().GetState(parcelID)
	if err != nil {
		return "", fmt.Errorf("failed to read parcel %s: %v", parcelID, err)
	}
	if parcelJSON == nil {
		return "", fmt.Errorf("parcel %s does not exist", parcelID)
	}
	var parcel Parcel
	if err := json.Unmarshal(parcelJSON, &parcel); err != nil {
		return "", fmt.Errorf("failed to unmarshal parcel: %v", err)
	}
	if parcel.OwnerID != sellerID {
		return "", fmt.Errorf("seller %s is not the current owner of parcel %s", sellerID, parcelID)
	}
	if parcel.Status != "ACTIVE" {
		return "", fmt.Errorf("parcel %s is not ACTIVE", parcelID)
	}

	existing, err := ctx.GetStub().GetState(requestID)
	if err != nil {
		return "", fmt.Errorf("failed to read transfer %s: %v", requestID, err)
	}
	if existing != nil {
		return "", fmt.Errorf("transfer request %s already exists", requestID)
	}

	txID := ctx.GetStub().GetTxID()
	now := time.Now().UTC().Format(time.RFC3339)

	transfer := TransferRequest{
		DocType:        "TRANSFER",
		RequestID:      requestID,
		ParcelID:       parcelID,
		SellerID:       sellerID,
		BuyerID:        buyerID,
		Status:         "SUBMITTED",
		SubmittedAt:    now,
		UpdatedAt:      now,
		BlockchainTxID: txID,
	}
	transferJSON, err := json.Marshal(transfer)
	if err != nil {
		return "", fmt.Errorf("failed to marshal transfer: %v", err)
	}
	if err := ctx.GetStub().PutState(requestID, transferJSON); err != nil {
		return "", fmt.Errorf("failed to put transfer state: %v", err)
	}

	// Composite-key index on (parcel_id, request_id) for history queries.
	historyKey, err := ctx.GetStub().CreateCompositeKey("PARCEL_TRANSFER", []string{parcelID, requestID})
	if err != nil {
		return "", fmt.Errorf("failed to create history composite key: %v", err)
	}
	if err := ctx.GetStub().PutState(historyKey, []byte{1}); err != nil {
		return "", fmt.Errorf("failed to put history index: %v", err)
	}

	return txID, nil
}

// ApproveTransfer marks a transfer as approved on the ledger.
// Arguments: request_id
func (lc *LandRegistryChaincode) ApproveTransfer(ctx contractapi.TransactionContextInterface,
	requestID string) (string, error) {

	if requestID == "" {
		return "", fmt.Errorf("request_id is required for ApproveTransfer")
	}

	transferJSON, err := ctx.GetStub().GetState(requestID)
	if err != nil {
		return "", fmt.Errorf("failed to read transfer %s: %v", requestID, err)
	}
	if transferJSON == nil {
		return "", fmt.Errorf("transfer request %s does not exist", requestID)
	}
	var transfer TransferRequest
	if err := json.Unmarshal(transferJSON, &transfer); err != nil {
		return "", fmt.Errorf("failed to unmarshal transfer: %v", err)
	}
	if transfer.Status != "SUBMITTED" {
		return "", fmt.Errorf("transfer %s is in status %s, expected SUBMITTED", requestID, transfer.Status)
	}

	txID := ctx.GetStub().GetTxID()
	now := time.Now().UTC().Format(time.RFC3339)

	transfer.Status = "APPROVED"
	transfer.UpdatedAt = now

	transferJSON, err = json.Marshal(transfer)
	if err != nil {
		return "", fmt.Errorf("failed to marshal transfer: %v", err)
	}
	if err := ctx.GetStub().PutState(requestID, transferJSON); err != nil {
		return "", fmt.Errorf("failed to put transfer state: %v", err)
	}
	return txID, nil
}

// ConfirmTransfer marks a transfer COMPLETED and updates the parcel owner.
// Arguments: request_id, tx_id
func (lc *LandRegistryChaincode) ConfirmTransfer(ctx contractapi.TransactionContextInterface,
	requestID, txID string) (string, error) {

	if requestID == "" || txID == "" {
		return "", fmt.Errorf("request_id and tx_id are required for ConfirmTransfer")
	}

	transferJSON, err := ctx.GetStub().GetState(requestID)
	if err != nil {
		return "", fmt.Errorf("failed to read transfer %s: %v", requestID, err)
	}
	if transferJSON == nil {
		return "", fmt.Errorf("transfer request %s does not exist", requestID)
	}
	var transfer TransferRequest
	if err := json.Unmarshal(transferJSON, &transfer); err != nil {
		return "", fmt.Errorf("failed to unmarshal transfer: %v", err)
	}
	if transfer.Status != "APPROVED" {
		return "", fmt.Errorf("transfer %s is in status %s, expected APPROVED", requestID, transfer.Status)
	}

	now := time.Now().UTC().Format(time.RFC3339)

	transfer.Status = "COMPLETED"
	transfer.BlockchainTxID = txID
	transfer.UpdatedAt = now
	transferJSON, err = json.Marshal(transfer)
	if err != nil {
		return "", fmt.Errorf("failed to marshal transfer: %v", err)
	}
	if err := ctx.GetStub().PutState(requestID, transferJSON); err != nil {
		return "", fmt.Errorf("failed to put transfer state: %v", err)
	}

	parcelJSON, err := ctx.GetStub().GetState(transfer.ParcelID)
	if err != nil {
		return "", fmt.Errorf("failed to read parcel %s: %v", transfer.ParcelID, err)
	}
	if parcelJSON == nil {
		return "", fmt.Errorf("parcel %s does not exist", transfer.ParcelID)
	}
	var parcel Parcel
	if err := json.Unmarshal(parcelJSON, &parcel); err != nil {
		return "", fmt.Errorf("failed to unmarshal parcel: %v", err)
	}
	parcel.OwnerID = transfer.BuyerID
	parcel.BlockchainTxID = txID
	parcel.UpdatedAt = now
	parcelJSON, err = json.Marshal(parcel)
	if err != nil {
		return "", fmt.Errorf("failed to marshal parcel: %v", err)
	}
	if err := ctx.GetStub().PutState(transfer.ParcelID, parcelJSON); err != nil {
		return "", fmt.Errorf("failed to put parcel state: %v", err)
	}

	return txID, nil
}

// GetParcel retrieves a parcel record from the ledger.
func (lc *LandRegistryChaincode) GetParcel(ctx contractapi.TransactionContextInterface,
	parcelID string) (*Parcel, error) {

	if parcelID == "" {
		return nil, fmt.Errorf("parcel_id is required for GetParcel")
	}
	parcelJSON, err := ctx.GetStub().GetState(parcelID)
	if err != nil {
		return nil, fmt.Errorf("failed to read parcel %s: %v", parcelID, err)
	}
	if parcelJSON == nil {
		return nil, fmt.Errorf("parcel %s does not exist", parcelID)
	}
	var parcel Parcel
	if err := json.Unmarshal(parcelJSON, &parcel); err != nil {
		return nil, fmt.Errorf("failed to unmarshal parcel: %v", err)
	}
	return &parcel, nil
}

// GetTransfer retrieves a transfer request from the ledger.
func (lc *LandRegistryChaincode) GetTransfer(ctx contractapi.TransactionContextInterface,
	requestID string) (*TransferRequest, error) {

	if requestID == "" {
		return nil, fmt.Errorf("request_id is required for GetTransfer")
	}
	transferJSON, err := ctx.GetStub().GetState(requestID)
	if err != nil {
		return nil, fmt.Errorf("failed to read transfer %s: %v", requestID, err)
	}
	if transferJSON == nil {
		return nil, fmt.Errorf("transfer request %s does not exist", requestID)
	}
	var transfer TransferRequest
	if err := json.Unmarshal(transferJSON, &transfer); err != nil {
		return nil, fmt.Errorf("failed to unmarshal transfer: %v", err)
	}
	return &transfer, nil
}

// GetParcelHistory retrieves all transfer events for a parcel.
// Reads the composite-key index PARCEL_TRANSFER~parcelID~requestID~ to locate
// every transfer for the parcel, then resolves each transfer record.
func (lc *LandRegistryChaincode) GetParcelHistory(ctx contractapi.TransactionContextInterface,
	parcelID string) ([]*TransferRequest, error) {

	if parcelID == "" {
		return nil, fmt.Errorf("parcel_id is required for GetParcelHistory")
	}

	iter, err := ctx.GetStub().GetStateByPartialCompositeKey("PARCEL_TRANSFER", []string{parcelID})
	if err != nil {
		return nil, fmt.Errorf("failed to query parcel history: %v", err)
	}
	defer iter.Close()

	var transfers []*TransferRequest
	for iter.HasNext() {
		queryResult, err := iter.Next()
		if err != nil {
			return nil, err
		}
		_, attrs, err := ctx.GetStub().SplitCompositeKey(queryResult.Key)
		if err != nil {
			return nil, fmt.Errorf("failed to split composite key %q: %v", queryResult.Key, err)
		}
		if len(attrs) != 2 {
			return nil, fmt.Errorf("unexpected composite key attributes: %v", attrs)
		}
		requestID := attrs[1]
		transferJSON, err := ctx.GetStub().GetState(requestID)
		if err != nil {
			return nil, err
		}
		if transferJSON == nil {
			continue
		}
		var transfer TransferRequest
		if err := json.Unmarshal(transferJSON, &transfer); err != nil {
			return nil, fmt.Errorf("failed to unmarshal transfer: %v", err)
		}
		transfers = append(transfers, &transfer)
	}

	if transfers == nil {
		transfers = []*TransferRequest{}
	}
	return transfers, nil
}

// VerifyTransaction verifies a transfer transaction on the ledger.
// Returns the transfer record; the caller must check Status == COMPLETED.
func (lc *LandRegistryChaincode) VerifyTransaction(ctx contractapi.TransactionContextInterface,
	requestID string) (*TransferRequest, error) {

	if requestID == "" {
		return nil, fmt.Errorf("request_id is required for VerifyTransaction")
	}
	return lc.GetTransfer(ctx, requestID)
}

// QueryParcelsByOwner retrieves all parcels owned by a given owner.
func (lc *LandRegistryChaincode) QueryParcelsByOwner(ctx contractapi.TransactionContextInterface,
	ownerID string) ([]*Parcel, error) {

	if ownerID == "" {
		return nil, fmt.Errorf("owner_id is required for QueryParcelsByOwner")
	}

	iter, err := ctx.GetStub().GetStateByPartialCompositeKey("PARCEL", []string{ownerID})
	if err != nil {
		return nil, fmt.Errorf("failed to query parcels by owner: %v", err)
	}
	defer iter.Close()

	var parcels []*Parcel
	for iter.HasNext() {
		queryResult, err := iter.Next()
		if err != nil {
			return nil, err
		}
		_, attrs, err := ctx.GetStub().SplitCompositeKey(queryResult.Key)
		if err != nil {
			return nil, fmt.Errorf("failed to split composite key: %v", err)
		}
		if len(attrs) != 2 {
			continue
		}
		parcelID := attrs[1]
		parcelJSON, err := ctx.GetStub().GetState(parcelID)
		if err != nil {
			return nil, err
		}
		if parcelJSON == nil {
			continue
		}
		var parcel Parcel
		if err := json.Unmarshal(parcelJSON, &parcel); err != nil {
			return nil, fmt.Errorf("failed to unmarshal parcel: %v", err)
		}
		parcels = append(parcels, &parcel)
	}

	if parcels == nil {
		parcels = []*Parcel{}
	}
	return parcels, nil
}
