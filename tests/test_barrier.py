# test_barrier_service.py

from services.barrier_service import BarrierService


def test_barrier_service():
    print("=" * 50)
    print("Testing BarrierService")
    print("=" * 50)

    barrier = BarrierService()

    print(f"\n📊 Status awal: {barrier.get_status()}")

    if not barrier.is_available:
        print("❌ Barrier tidak tersedia!")
        print("💡 Cek koneksi serial dan port")
        return

    input("\n📤 Press ENTER to open barrier...")

    success = barrier.open()

    if success:
        print("✅ Barrier opened successfully!")
    else:
        print("❌ Failed to open barrier!")

    print(f"\n📊 Status akhir: {barrier.get_status()}")

    barrier.close()


if __name__ == "__main__":
    test_barrier_service()
