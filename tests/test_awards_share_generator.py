"""DCA share images must be generated using real, public nomination entries."""
import struct
from io import BytesIO
from zipfile import ZipFile

from dca_rebuild.models import DCANominee, DCANominationSubmission


def _dimensions(response):
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data[:8] == bytes.fromhex("89504e470d0a1a0a")
    return struct.unpack(">II", response.data[16:24])


def test_awards_generate_feed_and_story_in_light_and_dark(website):
    client = website.test_client()
    for fmt, dims in (("story", (1080, 1920)), ("post", (1080, 1350))):
        for theme in ("light", "dark"):
            response = client.get(f"/social/awards/{fmt}/{theme}/awards.png")
            assert _dimensions(response) == dims
    options = client.get("/social/awards/options.json")
    assert options.status_code == 200
    assert len(options.get_json()["categories"]) == 27
    assert client.get("/social/awards/story/purple/awards.png").status_code == 404


def test_category_and_nominee_graphics_are_from_published_edition(website, database):
    engine, factory, edition_id = database
    from dca_rebuild.phase9e import CategoryStage9E
    from dca_rebuild.models import DCACategory
    with factory.begin() as db:
        category = db.query(DCACategory).filter_by(edition_id=edition_id).first()
        cid = category.id
        nominee = DCANominee(edition_id=edition_id, category_id=cid, name="Public Example",
                             normalized_name="public example", moderation_status="approved")
        db.add(nominee)
        db.flush()
        nid = nominee.id
        db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=nid,
                                       submitter_hash="one-supporter"))
    client = website.test_client()
    options = client.get("/social/awards/options.json").get_json()
    selected = next(x for x in options["categories"] if x["id"] == cid)
    assert any(x["id"] == nid and x["name"] == "Public Example" for x in selected["nominees"])
    assert _dimensions(client.get(f"/social/awards/story/dark/category.png?category={cid}")) == (1080, 1920)
    assert _dimensions(client.get(f"/social/awards/post/light/nominees.png?category={cid}")) == (1080, 1350)
    assert _dimensions(client.get(f"/social/awards/story/light/nominee.png?category={cid}&nominee={nid}")) == (1080, 1920)
    assert client.get("/social/awards/story/light/nominee.png?category=999999&nominee=1").status_code == 404
    assert client.get(f"/social/awards/story/light/nominee.png?category={cid}&nominee=999999").status_code == 404


def test_awards_share_interface_has_four_scopes_and_user_theme_switch(website):
    html = website.test_client().get("/awards/dancers-choice/2026").get_data(as_text=True)
    assert 'id="lfv-awards-controls"' in html
    for scope in ("awards", "category", "nominees", "nominee"):
        assert f'value="{scope}"' in html
    assert 'value="dark"' in html
    assert 'value="light"' in html
    assert 'data-lfv-format="story"' in html
    assert 'data-lfv-format="post"' in html


def test_bundle_is_a_zip_of_generated_nominee_images(website, database):
    from dca_rebuild.models import DCACategory
    with database[1]() as db:
        category = db.query(DCACategory).filter_by(edition_id=database[2]).first()
        cid = category.id
    response = website.test_client().get(
        f"/social/awards/bundle.zip?format=story&theme=dark&scope=nominees&category={cid}"
    )
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    with ZipFile(BytesIO(response.data)) as archive:
        files = archive.namelist()
        assert files
        assert archive.read(files[0])[:8] == bytes.fromhex("89504e470d0a1a0a")
