import asyncio
import numpy as np
import open3d as o3d
from aiortc import RTCPeerConnection, RTCDataChannel
# Configure TSDF volume parameters
voxel_length = 0.01  # 1 cm voxels for urban XR
sdf_trunc = 0.04
tsdf = o3d.pipelines.integration.ScalableTSDFVolume(
    voxel_length=voxel_length,
    sdf_trunc=sdf_trunc,
    color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)

async def stream_worker(data_channel: RTCDataChannel):
    while True:
        mesh = extract_mesh_snapshot()  # thread-safe snapshot function
        pts = np.asarray(mesh.vertices, dtype=np.float32)
        # simple binary format: count + interleaved xyz (little-endian)
        payload = pts.tobytes()
        header = len(pts).to_bytes(4, 'little')
        data_channel.send(header + payload)  # non-blocking
        await asyncio.sleep(0.2)  # 5 Hz mesh updates

def integrate_frame(depth, color, intrinsics, extrinsics):
    # depth: np.uint16 or float32 depth in meters; color: uint8 HxWx3
    depth_o3d = o3d.geometry.Image(depth)
    color_o3d = o3d.geometry.Image(color)
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        color_o3d, depth_o3d, convert_rgb_to_intensity=False)
    intr = o3d.camera.PinholeCameraIntrinsic(*intrinsics)  # fx,fy,cx,cy,h,w
    tsdf.integrate(rgbd, intr, np.linalg.inv(extrinsics))  # world->camera

def extract_mesh_snapshot():
    mesh = tsdf.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    return mesh

# Example entry point to attach to WebRTC peer
async def run_server(peer: RTCPeerConnection):
    dc = peer.createDataChannel("recon")
    dc.on("open")(lambda: asyncio.create_task(stream_worker(dc)))
    # Peer connection setup (SDP exchange) handled externally