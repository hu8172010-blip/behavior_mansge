import torch


def verify_cuda() -> dict[str, object]:
    assert torch.version.cuda is not None
    assert torch.cuda.is_available()

    value = torch.tensor([2.0], device="cuda") * 3
    properties = torch.cuda.get_device_properties(0)
    assert properties.total_memory >= 7 * 1024**3

    return {
        "cuda_version": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "device_name": torch.cuda.get_device_name(0),
        "tensor_result": value.cpu().item(),
        "total_memory": properties.total_memory,
    }


if __name__ == "__main__":
    print(verify_cuda())
