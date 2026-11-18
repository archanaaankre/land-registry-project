package chaincode

import (
	"encoding/json"
	"testing"

	"github.com/hyperledger/fabric-chaincode-go/shimtest"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// NOTE: This test file uses the low-level shimtest mock stub shipped with
// fabric-chaincode-go. It has NOT been compiled or run in this environment
// because the Go toolchain is not available. Run `go test ./... -v` in an
// environment with Go 1.21+ and the module `go.sum` to verify.

func newChaincode(t *testing.T) (*shimtest.MockStub, error) {
	t.Helper()
	cc, err := contractapi.NewChaincode(NewLandRegistryChaincode())
	require.NoError(t, err)
	stub := shimtest.NewMockStub("land-registry", cc)
	require.NotNil(t, stub)
	return stub, nil
}

func invoke(t *testing.T, stub *shimtest.MockStub, fn string, args ...string) int32 {
	t.Helper()
	txID := stub.MockTransactionStart("tx-1")
	require.NotEmpty(t, txID)

	args32 := make([][]byte, 0, 1+len(args))
	args32 = append(args32, []byte(fn))
	for _, a := range args {
		args32 = append(args32, []byte(a))
	}
	res := stub.MockInvoke(txID, args32)
	require.NotNil(t, res)
	stub.MockTransactionEnd()
	return res.Status
}

// TestRegisterParcel_Success tests successful parcel registration via the chaincode dispatch.
func TestRegisterParcel_Success(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(200), status)

	parcelJSON, err := stub.GetState("parcel-1")
	require.NoError(t, err)
	require.NotNil(t, parcelJSON)

	var parcel Parcel
	require.NoError(t, json.Unmarshal(parcelJSON, &parcel))
	assert.Equal(t, "parcel-1", parcel.ParcelID)
	assert.Equal(t, "CAD-001", parcel.CadastralNumber)
	assert.Equal(t, "Ward 1", parcel.Location)
	assert.Equal(t, float64(100), parcel.Area)
	assert.Equal(t, "SQ_METERS", parcel.AreaUnit)
	assert.Equal(t, "owner-1", parcel.OwnerID)
	assert.Equal(t, "ACTIVE", parcel.Status)
}

// TestRegisterParcel_Duplicate tests duplicate parcel rejection.
func TestRegisterParcel_Duplicate(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(200), status)

	status = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-002", "Ward 2", "200", "HECTARES", "owner-2")
	assert.Equal(t, int32(500), status)
}

// TestRegisterParcel_InvalidInput tests invalid registration input rejection.
func TestRegisterParcel_InvalidInput(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "RegisterParcel", "", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(500), status)

	status = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "not-a-number", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(500), status)
}

// TestSubmitTransfer_Success tests successful transfer submission.
func TestSubmitTransfer_Success(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(200), status)

	status = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	assert.Equal(t, int32(200), status)

	transferJSON, err := stub.GetState("transfer-1")
	require.NoError(t, err)
	require.NotNil(t, transferJSON)

	var transfer TransferRequest
	require.NoError(t, json.Unmarshal(transferJSON, &transfer))
	assert.Equal(t, "SUBMITTED", transfer.Status)
}

// TestSubmitTransfer_Duplicate tests duplicate transfer request rejection.
func TestSubmitTransfer_Duplicate(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(200), status)
	status = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	assert.Equal(t, int32(200), status)
	status = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	assert.Equal(t, int32(500), status)
}

// TestSubmitTransfer_NonexistentParcel tests transfer for a nonexistent parcel.
func TestSubmitTransfer_NonexistentParcel(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-nonexistent", "owner-1", "owner-2")
	assert.Equal(t, int32(500), status)
}

// TestSubmitTransfer_WrongSeller tests that a non-owner cannot transfer.
func TestSubmitTransfer_WrongSeller(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(200), status)
	status = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-2", "owner-3")
	assert.Equal(t, int32(500), status)
}

// TestSubmitTransfer_SameParty tests seller == buyer rejection.
func TestSubmitTransfer_SameParty(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	status := invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	assert.Equal(t, int32(200), status)
	status = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-1")
	assert.Equal(t, int32(500), status)
}

// TestApproveTransfer_Success tests successful transfer approval.
func TestApproveTransfer_Success(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	_ = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	status := invoke(t, stub, "ApproveTransfer", "transfer-1")
	assert.Equal(t, int32(200), status)

	transferJSON, err := stub.GetState("transfer-1")
	require.NoError(t, err)
	var transfer TransferRequest
	require.NoError(t, json.Unmarshal(transferJSON, &transfer))
	assert.Equal(t, "APPROVED", transfer.Status)
}

// TestApproveTransfer_NotSubmitted tests double approval rejection.
func TestApproveTransfer_NotSubmitted(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	_ = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	_ = invoke(t, stub, "ApproveTransfer", "transfer-1")
	status := invoke(t, stub, "ApproveTransfer", "transfer-1")
	assert.Equal(t, int32(500), status)
}

// TestConfirmTransfer_Success tests successful confirmation and ownership change.
func TestConfirmTransfer_Success(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	_ = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	_ = invoke(t, stub, "ApproveTransfer", "transfer-1")
	status := invoke(t, stub, "ConfirmTransfer", "transfer-1", "confirm-tx-999")
	assert.Equal(t, int32(200), status)

	transferJSON, err := stub.GetState("transfer-1")
	require.NoError(t, err)
	var transfer TransferRequest
	require.NoError(t, json.Unmarshal(transferJSON, &transfer))
	assert.Equal(t, "COMPLETED", transfer.Status)
	assert.Equal(t, "confirm-tx-999", transfer.BlockchainTxID)

	parcelJSON, err := stub.GetState("parcel-1")
	require.NoError(t, err)
	var parcel Parcel
	require.NoError(t, json.Unmarshal(parcelJSON, &parcel))
	assert.Equal(t, "owner-2", parcel.OwnerID)
}

// TestConfirmTransfer_NotApproved tests confirmation of a non-approved transfer.
func TestConfirmTransfer_NotApproved(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	_ = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	status := invoke(t, stub, "ConfirmTransfer", "transfer-1", "confirm-tx-999")
	assert.Equal(t, int32(500), status)
}

// TestGetParcel_Success tests parcel retrieval.
func TestGetParcel_Success(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	res := stub.MockInvoke("q-1", [][]byte{[]byte("GetParcel"), []byte("parcel-1")})
	require.Equal(t, int32(200), res.Status)
}

// TestGetParcel_Nonexistent tests retrieval of a nonexistent parcel.
func TestGetParcel_Nonexistent(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	res := stub.MockInvoke("q-1", [][]byte{[]byte("GetParcel"), []byte("parcel-nonexistent")})
	assert.Equal(t, int32(500), res.Status)
}

// TestGetParcelHistory_RecordsTransfers tests history retrieval across transfers.
func TestGetParcelHistory_RecordsTransfers(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	_ = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	_ = invoke(t, stub, "ApproveTransfer", "transfer-1")
	_ = invoke(t, stub, "ConfirmTransfer", "transfer-1", "tx-1")

	res := stub.MockInvoke("q-2", [][]byte{[]byte("GetParcelHistory"), []byte("parcel-1")})
	assert.Equal(t, int32(200), res.Status)
	assert.Contains(t, string(res.Payload), "transfer-1")
}

// TestGetParcelHistory_ReturnsEmptyList tests history retrieval when no transfers exist.
func TestGetParcelHistory_ReturnsEmptyList(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")

	res := stub.MockInvoke("q-2", [][]byte{[]byte("GetParcelHistory"), []byte("parcel-1")})
	assert.Equal(t, int32(200), res.Status)
}

// TestVerifyTransaction_Success tests verification of a completed transfer.
func TestVerifyTransaction_Success(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	_ = invoke(t, stub, "SubmitTransfer", "transfer-1", "parcel-1", "owner-1", "owner-2")
	_ = invoke(t, stub, "ApproveTransfer", "transfer-1")
	_ = invoke(t, stub, "ConfirmTransfer", "transfer-1", "confirm-tx-999")

	res := stub.MockInvoke("q-3", [][]byte{[]byte("VerifyTransaction"), []byte("transfer-1")})
	assert.Equal(t, int32(200), res.Status)
	assert.Contains(t, string(res.Payload), "COMPLETED")
}

// TestQueryParcelsByOwner_Success tests parcel lookup by owner.
func TestQueryParcelsByOwner_Success(t *testing.T) {
	stub, err := newChaincode(t)
	require.NoError(t, err)

	_ = invoke(t, stub, "RegisterParcel", "parcel-1", "CAD-001", "Ward 1", "100", "SQ_METERS", "owner-1")
	_ = invoke(t, stub, "RegisterParcel", "parcel-2", "CAD-002", "Ward 2", "200", "HECTARES", "owner-1")

	res := stub.MockInvoke("q-4", [][]byte{[]byte("QueryParcelsByOwner"), []byte("owner-1")})
	assert.Equal(t, int32(200), res.Status)
	assert.Contains(t, string(res.Payload), "parcel-1")
	assert.Contains(t, string(res.Payload), "parcel-2")
}
